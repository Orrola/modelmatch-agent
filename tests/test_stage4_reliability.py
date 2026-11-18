"""Offline SDK regressions; synthetic metadata is not live provider verification."""

import asyncio
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from agents import AgentOutputSchema
from agents.models.chatcmpl_converter import Converter
from litellm.utils import get_optional_params

from modelmatch_agents import create_team
from modelmatch_schemas import DispatchComplete, Followup, OrchestrationLimits, WriterOutput
from modelmatch_web import WebHooks
from orchestration import ModelMatchWorkflow
from tests.fake_modelmatch import CapturingRunner, ScriptedModel, USER_INPUT
from tools.artificial_analysis import load_mock_snapshot
from tools.run_diagnostics import failure_details, inspect_structured_output
from vertex_runtime import CallBudget, MeteredModel, PROVIDER_METADATA, VertexConfig, safe_error

FIXTURE = Path(__file__).parent / "fixtures/phase2a_synthetic.json"


class SyntheticQuotaError(RuntimeError):
    status_code = 429

    def __init__(self, retry_after=None):
        super().__init__("SYNTHETIC_PRIVATE_BODY")
        self.response = SimpleNamespace(headers={"Authorization": "SYNTHETIC_PRIVATE_HEADER"})
        if retry_after is not None:
            self.response.headers["Retry-After"] = retry_after


class WriterModel(ScriptedModel):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.writer_attempts = 0

    async def get_response(self, system_instructions, *args, **kwargs):
        if "Select an evidence-grounded recommendation" not in system_instructions:
            return await super().get_response(system_instructions, *args, **kwargs)
        self.writer_attempts += 1
        if self.mode == "quota":
            raise SyntheticQuotaError("7")
        if self.mode == "timeout":
            raise TimeoutError("SYNTHETIC_PRIVATE_BODY")
        response = await super().get_response(system_instructions, *args, **kwargs)
        PROVIDER_METADATA.get().update(finish_reason="length" if self.mode == "length" else "stop",
                                       reasoning_tokens=1966 if self.mode == "length" else None)
        if self.mode in ("length", "syntax"):
            response.output[0].content[0].text = '{"candidate_ids": ['
        elif self.mode == "schema":
            response.output[0].content[0].text = json.dumps({
                "candidate_ids": 123, "evidence_ids": [], "validation_steps": ["task_pilot"]})
        elif self.mode == "evidence":
            data = json.loads(response.output[0].content[0].text)
            data["evidence_ids"] = data["evidence_ids"][:-1]
            response.output[0].content[0].text = json.dumps(data)
        return response


class FollowupModel(ScriptedModel):
    def __init__(self, tasks, *, wait=False):
        super().__init__(followups=tasks)
        self.followup_roles = set()
        self.followup_barrier = asyncio.Event()
        self.cancelled_roles = set()
        self.wait = wait

    async def get_response(self, system_instructions, input, *args, **kwargs):
        payload = self.payload(input)
        if payload.get("fresh_context") and payload.get("target_model_ids"):
            role = "A" if "Retrieve original General Intelligence" in system_instructions else "B" if "Map the concrete task" in system_instructions else "C"
            self.followup_roles.add(role)
            if len(self.followup_roles) == 3:
                self.followup_barrier.set()
            try:
                await self.followup_barrier.wait()
                if self.wait:
                    await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled_roles.add(role)
                raise
        return await super().get_response(system_instructions, input, *args, **kwargs)


class SplitFollowupModel(ScriptedModel):
    async def get_response(self, system_instructions, input, *args, **kwargs):
        payload = self.payload(input)
        if payload.get("stage") == "followup":
            count = self.counts.get("split_followup", 0)
            self.counts["split_followup"] = count + 1
            if count < len(self.followups):
                task = self.followups[count]
                return self.tools([(f"research_{task.role.lower()}", {
                    "task": task.task, "model_ids": task.model_ids})])
            return self.text(DispatchComplete(completed=True))
        return await super().get_response(system_instructions, input, *args, **kwargs)


class WriterConfigurationTests(unittest.TestCase):
    def test_actual_writer_settings_pass_the_public_litellm_gate_with_strict_schema(self):
        config = VertexConfig("synthetic-project")
        settings = config.settings()
        team = create_team(ScriptedModel(), ScriptedModel(), settings)
        writer = team.writer.model_settings
        self.assertIsNone(settings.reasoning)
        self.assertNotIn("allowed_openai_params", settings.extra_args)
        self.assertEqual(writer.reasoning.effort, "low")
        self.assertEqual(writer.extra_args["timeout"], 30)
        self.assertEqual(writer.extra_args["num_retries"], 0)
        self.assertEqual(writer.max_tokens, 2048)
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
             patch("socket.getaddrinfo", side_effect=AssertionError("Network forbidden")):
            mapped = get_optional_params(model=config.model, custom_llm_provider="vertex_ai",
                reasoning_effort=writer.reasoning.effort, max_tokens=writer.max_tokens,
                allowed_openai_params=writer.extra_args["allowed_openai_params"],
                response_format=Converter.convert_response_format(AgentOutputSchema(WriterOutput)))
        self.assertEqual(mapped["thinkingConfig"]["thinkingLevel"], "low")
        self.assertEqual(mapped["max_output_tokens"], 2048)
        self.assertEqual(mapped["response_mime_type"], "application/json")
        self.assertEqual(mapped["response_json_schema"]["required"], list(WriterOutput.model_fields))
        self.assertFalse(mapped["response_json_schema"]["additionalProperties"])
        for agent in (team.lead, *team.researchers.values()):
            self.assertEqual(agent.model_settings.reasoning, settings.reasoning)
            self.assertEqual(agent.model_settings.max_tokens, settings.max_tokens)
            self.assertEqual(agent.model_settings.extra_args, settings.extra_args)
        self.assertTrue(team.lead.model_settings.parallel_tool_calls)

    def test_writer_diagnostics_do_not_repair_json_or_retain_private_values(self):
        response = SimpleNamespace(output=[SimpleNamespace(type="reasoning", text="SYNTHETIC_PRIVATE_REASONING"),
            SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text='```json\n{}\n```')])])
        diagnostic = inspect_structured_output(response, None, WriterOutput)
        self.assertEqual(diagnostic["failure_category"], "malformed_json")
        self.assertEqual(diagnostic["generation_status"], "unknown")
        self.assertTrue(diagnostic["markdown_fence_present"])
        self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(diagnostic))

    def test_quota_metadata_does_not_invent_a_retry_delay_or_leak_headers(self):
        for header, expected in ((None, None), ("7", 7), ("-1", None), ("nan", None),
                                 ("inf", None), ("Mon, 16 Nov 2026 18:00:00 GMT", None)):
            error = SyntheticQuotaError(header)
            result = safe_error(error)
            self.assertEqual(result["category"], "quota_or_rate_limit")
            self.assertEqual(result["retry_after_seconds"], expected)
            self.assertEqual(result["retry_after_present"], header is not None)
            self.assertEqual(failure_details(error)["category"], "quota_or_rate_limit")
            self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(result))


class Stage4WorkflowTests(unittest.IsolatedAsyncioTestCase):
    def workflow(self, model, *, hooks=None, metered=False):
        snapshot = load_mock_snapshot(FIXTURE)
        self.runner = CapturingRunner()
        self.budget = CallBudget()
        config = VertexConfig("synthetic-project")
        wrapped = MeteredModel(model, config.model, self.budget, config) if metered else model
        return ModelMatchWorkflow(wrapped, wrapped, settings=config.settings(), hooks=hooks, runner=self.runner,
            snapshot_loader=AsyncMock(return_value=snapshot), limits=OrchestrationLimits(timeout_seconds=10))

    def tasks(self):
        return [Followup(role=role, task=f"Inspect targeted {role} evidence", reason="Synthetic evidence gap.",
                         model_ids=["synthetic-finance"]) for role in ("A", "B", "C")]

    async def test_writer_failures_are_precise_and_never_accepted_or_retried(self):
        expected = {"length": "incomplete_generation", "syntax": "malformed_json",
                    "schema": "schema_validation_error", "evidence": "evidence_validation_error",
                    "quota": "quota_or_rate_limit", "timeout": "timeout"}
        for mode, category in expected.items():
            with self.subTest(mode=mode):
                model = WriterModel(mode)
                result = await self.workflow(model, metered=True).run(USER_INPUT)
                self.assertEqual(model.writer_attempts, 1)
                self.assertTrue(result["writer_fallback"])
                self.assertEqual(result["writer_error"]["category"], category)
                self.assertEqual(result["diagnostics"]["stages"]["writer"]["status"], "fallback")
                self.assertFalse(any(e["stage"] == "writer" and e["status"] == "accepted"
                                     for e in result["diagnostics"]["events"]))
                self.assertEqual(result["diagnostics"]["stages"]["decision"]["status"], "accepted")
                self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(result))
                record = next(r for r in self.budget.records if r["stage"] == "writer")
                if mode == "length":
                    self.assertEqual(record["finish_reason"], "length")
                    self.assertEqual(record["reasoning_tokens"], 1966)
                    self.assertEqual(result["writer_error"]["output_diagnostics"]["validation_category"], "malformed_json")
                if mode == "quota":
                    self.assertEqual(record["error"]["retry_after_seconds"], 7)
                    self.assertIsNone(record["finish_reason"])
                    self.assertNotIn("usage", record)
                if mode == "evidence":
                    self.assertEqual(result["writer_error"]["validation_code"], "evidence_set_mismatch")
                    self.assertEqual(record["output_diagnostics"]["validation_category"], "valid")
                if mode == "schema":
                    self.assertTrue(any(e["path"] == ["candidate_ids"]
                                        for e in result["writer_error"]["output_diagnostics"]["schema_errors"]))

    async def test_complete_writer_output_is_accepted_with_unchanged_evidence(self):
        from recommendation import writer_payload
        model = WriterModel("accepted")
        result = await self.workflow(model, metered=True).run(USER_INPUT)
        self.assertFalse(result["writer_fallback"])
        self.assertEqual(result["diagnostics"]["stages"]["writer"]["status"], "accepted")
        record = next(r for r in self.budget.records if r["stage"] == "writer")
        self.assertEqual(record["output_diagnostics"]["validation_category"], "valid")
        for eid in writer_payload(result["decision"], result["selection"])["evidence_ids"]:
            self.assertIn(eid, result["markdown"])

    async def test_authorized_controller_batch_has_parallel_fresh_contexts_and_sdk_traces(self):
        emitted = []
        hooks = WebHooks(emitted.append)
        model = FollowupModel(self.tasks())
        workflow = self.workflow(model, hooks=hooks)
        lead = workflow.team.lead
        result = await workflow.run(USER_INPUT)
        self.assertNotEqual(result["status"], "error", result.get("error"))
        self.assertEqual(model.followup_roles, {"A", "B", "C"})
        self.assertIs(workflow.team.lead, lead)
        self.assertEqual([r["stage"] for r in result["reviews"]], ["review", "review_final"])
        calls = [c for c in self.runner.calls if c["agent"].name == "Lead"]
        self.assertTrue(all(c["agent"] is lead and c["context"] is workflow.lead_context for c in calls))
        self.assertFalse(any(c["stage"] == "followup" for c in calls))
        initial = next(b for b in workflow.batches if b["stage"] == "dispatch")
        self.assertEqual(set(initial["calls"]), {"research_a", "research_b", "research_c"})
        batch = next(b for b in workflow.batches if b["stage"] == "followup")
        self.assertEqual(batch["source"], "controller")
        self.assertEqual(set(batch["calls"]), {"research_a", "research_b", "research_c"})
        starts = [e for e in result["trace"] if e["type"] == "researcher_start" and e["round_number"] == 1]
        ends = [e for e in result["trace"] if e["type"] == "researcher_end" and e["context_id"] in {s["context_id"] for s in starts}]
        self.assertEqual(len(starts), 3)
        self.assertEqual(len({e["context_id"] for e in starts}), 3)
        self.assertEqual(len({e["context_id"] for e in result["trace"] if e["type"] == "researcher_start"}), 6)
        self.assertLess(max(e["monotonic"] for e in starts), min(e["monotonic"] for e in ends))
        controller_calls = [c for c in hooks.calls if c.get("origin") == "controller"]
        self.assertEqual(len(controller_calls), 3)
        self.assertTrue(all(c["status"] == "completed" and c["elapsed_seconds"] is not None for c in controller_calls))
        self.assertEqual({c["tool"] for c in controller_calls}, set(batch["calls"]))
        self.assertEqual(result["researcher_runs"], 6)
        self.assertEqual(result["reviews"][-1]["audit"]["controller_followup"]["source"], "controller")
        self.assertFalse(workflow._controller_dispatch_active)

    async def test_split_model_turns_still_fail_batch_acceptance(self):
        model = SplitFollowupModel(followups=self.tasks())
        workflow = self.workflow(model)
        # Replay the former model-controlled path with the real SDK Runner.
        async def legacy_dispatch(tasks):
            await workflow.lead("followup", {"plan": workflow.plan.model_dump(),
                "tasks": [t.model_dump() for t in tasks], "required_roles": [t.role for t in tasks]})
        workflow._controller_followup = legacy_dispatch
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["error"], "researchers_not_dispatched_in_one_model_turn")
        self.assertEqual([b["calls"] for b in workflow.batches if b["stage"] == "followup"],
                         [["research_a"], ["research_b"], ["research_c"]])
        self.assertEqual(result["diagnostics"]["stages"]["parse"]["status"], "accepted")
        self.assertEqual(result["diagnostics"]["stages"]["followup"]["status"], "failed")
        self.assertEqual(result["diagnostics"]["stages"]["decision"]["status"], "not_reached")

    async def test_disabled_controller_tool_is_rejected_before_any_followup_generation(self):
        workflow = self.workflow(ScriptedModel(followups=self.tasks()))
        original = workflow._controller_followup
        async def disable(tasks):
            next(t for t in workflow.team.lead.tools if t.name == "research_c").is_enabled = False
            return await original(tasks)
        workflow._controller_followup = disable
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["error"], "research_dispatch_not_allowed")
        self.assertEqual(result["researcher_runs"], 3)
        self.assertFalse(workflow._controller_dispatch_active)

    async def test_controller_rechecks_exact_authorization_and_preserves_scope(self):
        workflow = self.workflow(ScriptedModel(followups=self.tasks()))
        original = workflow._controller_followup
        async def tamper(tasks):
            return await original([tasks[0].model_copy(update={"task": "Unauthorized change"}), *tasks[1:]])
        workflow._controller_followup = tamper
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["error"], "research_dispatch_not_authorized")
        self.assertEqual(result["researcher_runs"], 3)

    async def test_unknown_scope_is_rejected_before_any_controller_child_starts(self):
        tasks = self.tasks()
        tasks[-1].model_ids = ["unknown-model-id"]
        workflow = self.workflow(ScriptedModel(followups=tasks))
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["error"], "unknown_model_id")
        self.assertEqual(result["researcher_runs"], 3)
        self.assertFalse(any(e["type"] == "researcher_start" and e["round_number"] == 1 for e in result["trace"]))

    async def test_cancellation_stops_all_controller_children(self):
        model = FollowupModel(self.tasks(), wait=True)
        workflow = self.workflow(model)
        task = asyncio.create_task(workflow.run(USER_INPUT))
        await asyncio.wait_for(model.followup_barrier.wait(), timeout=3)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(model.cancelled_roles, {"A", "B", "C"})
        self.assertFalse(workflow._controller_dispatch_active)
        self.assertTrue(workflow._closed)
        self.assertEqual(workflow.diagnostics.states["followup"]["status"], "cancelled")
