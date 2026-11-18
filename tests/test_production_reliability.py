"""Offline reliability regressions; synthetic failures are not live provider evidence."""

import asyncio
import json
import os
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import httpx
from agents import ModelSettings
from agents.usage import Usage

import app as web
from modelmatch_schemas import Followup, OrchestrationLimits, StatedNumber
from orchestration import ModelMatchWorkflow
from tests.fake_modelmatch import CapturingRunner, ScriptedModel, USER_INPUT, default_plan
from tools.artificial_analysis import load_mock_snapshot
from tools.run_diagnostics import AccessQueryFilter, CALL_CONTEXT, failure_details
from tools.task_classification import resolve_task_type
from vertex_runtime import BudgetExceeded, CallBudget, MeteredModel, VertexConfig, create_models


class ProviderFailure(RuntimeError):
    status_code = 503


class WriterFailureModel(ScriptedModel):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.writer_attempts = 0

    async def get_response(self, system_instructions, *args, **kwargs):
        if "Select an evidence-grounded recommendation" in system_instructions:
            self.writer_attempts += 1
            if self.mode == "provider":
                raise ProviderFailure("SIMULATED_PRIVATE_ERROR")
            if self.mode == "timeout":
                raise TimeoutError("SIMULATED_PRIVATE_ERROR")
            if self.mode == "schema":
                return self.text({"candidate_ids": [], "evidence_ids": [], "validation_steps": ["invalid-code"]})
            if self.mode == "malformed":
                response = self.text({})
                response.output[0].content[0].text = '{"candidate_ids": ['
                return response
            payload = self.payload(args[0] if args else kwargs["input"])
            value = {"candidate_ids": payload["candidate_ids"], "evidence_ids": payload["evidence_ids"], "validation_steps": ["task_pilot"]}
            if self.mode == "omit_evidence":
                value["evidence_ids"] = value["evidence_ids"][:-1]
            elif self.mode == "extra_evidence":
                value["evidence_ids"] = value["evidence_ids"] + ["synthetic-invented-reference"]
            elif self.mode == "candidate":
                value["candidate_ids"] = ["synthetic-altered-candidate"]
            elif self.mode == "validation":
                value["validation_steps"] = []
            return self.text(value)
        return await super().get_response(system_instructions, *args, **kwargs)


class ClassificationPolicyTests(unittest.TestCase):
    def test_overlapping_proposals_resolve_identically_across_multiple_domains(self):
        cases = {"Analyze financial documents.": "specialized_domain",
                 "Review clinical research.": "specialized_domain",
                 "Evaluate legal clauses.": "specialized_domain",
                 "Review engineering specifications.": "specialized_domain",
                 "Compare abstract logical arguments.": "reasoning_analysis",
                 "Compare legal and medical policies across domains.": "mixed_or_unknown",
                 "Help with unrelated tasks.": "mixed_or_unknown",
                 "Draft a greeting.": "mixed_or_unknown"}
        for raw, expected in cases.items():
            for proposed in ("reasoning_analysis", "specialized_domain", "mixed_or_unknown"):
                self.assertEqual(resolve_task_type(raw, proposed)[0], expected)

    def test_explicit_other_primary_types_and_operational_fields_are_preserved(self):
        for primary in ("tool_agent", "coding_assistant", "general_assistant"):
            self.assertEqual(resolve_task_type(USER_INPUT, primary)[0], primary)
        suffix = "\n\nStructured requirements (explicit user inputs; authoritative for these fields):\nlegal medical"
        self.assertEqual(resolve_task_type(USER_INPUT + suffix, "mixed_or_unknown")[0], "specialized_domain")

    def test_compatibility_access_logs_redact_query_text(self):
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
            ("local", "GET", "/run?question=SIMULATED_PRIVATE_QUERY", "1.1", 200), None)
        self.assertTrue(AccessQueryFilter().filter(record))
        self.assertIn("GET /run", record.getMessage())
        self.assertNotIn("SIMULATED_PRIVATE_QUERY", record.getMessage())


class WorkflowReliabilityTests(unittest.IsolatedAsyncioTestCase):
    def workflow(self, model=None):
        model = model or ScriptedModel()
        self.runner = CapturingRunner()
        snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        return ModelMatchWorkflow(model, model, runner=self.runner, snapshot_loader=AsyncMock(return_value=snapshot),
                                  limits=OrchestrationLimits(timeout_seconds=10))

    async def test_writer_failures_keep_exact_categories_and_strict_validation(self):
        modes = {"provider": ("provider_error", None), "timeout": ("timeout", None),
                 "schema": ("schema_validation_error", None), "malformed": ("schema_validation_error", None),
                 "omit_evidence": ("evidence_validation_error", "evidence_set_mismatch"),
                 "extra_evidence": ("evidence_validation_error", "evidence_set_mismatch"),
                 "candidate": ("evidence_validation_error", "candidate_order_mismatch"),
                 "validation": ("evidence_validation_error", "validation_steps_missing")}
        for mode, (category, rule) in modes.items():
            with self.subTest(mode=mode):
                model = WriterFailureModel(mode)
                result = await self.workflow(model).run(USER_INPUT)
                self.assertEqual(model.writer_attempts, 1)
                self.assertTrue(result["writer_fallback"])
                self.assertEqual(result["writer_error"]["category"], category)
                self.assertEqual(result["writer_error"]["validation_code"], rule)
                self.assertEqual(result["diagnostics"]["stages"]["writer"]["status"], "fallback")
                self.assertEqual(result["diagnostics"]["stages"]["decision"]["status"], "accepted")
                self.assertNotIn("SIMULATED_PRIVATE_ERROR", json.dumps(result))
                self.assertNotIn("synthetic-invented-reference", result["markdown"])

    async def test_generation_completion_precedes_controller_acceptance(self):
        result = await self.workflow().run(USER_INPUT)
        events = result["diagnostics"]["events"]
        for stage in ("parse", "dispatch", "A", "B", "C", "review", "writer"):
            statuses = [e["status"] for e in events if e["stage"] == stage]
            self.assertEqual(statuses, ["running", "completed", "accepted"])
        states = result["diagnostics"]["stages"]
        self.assertEqual(states["review_final"]["status"], "skipped")
        self.assertEqual(states["decision_gate"]["status"], "accepted")
        self.assertTrue(states["writer"]["started_at"])
        self.assertTrue(states["writer"]["accepted_at"])

    async def test_duplicate_followup_blocks_after_generation_without_claiming_acceptance(self):
        task = Followup(role="B", task="Inspect evidence", reason="Check gaps")
        result = await self.workflow(ScriptedModel(followups=[task, task])).run(USER_INPUT)
        self.assertEqual(result["error"], "invalid_or_over_budget_followup")
        state = result["diagnostics"]["stages"]["review"]
        self.assertEqual(state["rule"], "duplicate_followup_roles")
        self.assertEqual(state["status"], "failed")
        self.assertEqual(result["diagnostics"]["stages"]["decision"]["status"], "not_reached")
        self.assertFalse(any(e["type"] == "decision_started" for e in result["trace"]))

    async def test_research_failure_has_a_specific_decision_gate_and_no_writer(self):
        result = await self.workflow(ScriptedModel(fail_roles=["A"])).run(USER_INPUT)
        self.assertEqual(result["diagnostics"]["stages"]["decision_gate"]["code"], "researcher_evidence_incomplete")
        self.assertEqual(result["diagnostics"]["stages"]["A"]["status"], "failed")
        self.assertEqual(result["diagnostics"]["stages"]["writer"]["status"], "not_reached")

    async def test_accepted_review_does_not_bypass_conflicting_evidence(self):
        workflow = self.workflow()
        original = workflow.review_payload
        def corrupt_role_evidence():
            payload = original()
            model_id = next(iter(workflow.role_results["A"]["models"]))
            workflow.role_results["A"]["models"][model_id]["G"] = -999
            return payload
        workflow.review_payload = corrupt_role_evidence
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["error"], "researcher_evidence_conflict")
        self.assertEqual(result["diagnostics"]["stages"]["review"]["status"], "accepted")
        self.assertEqual(result["diagnostics"]["blocking_failure"]["rule"], "researcher_evidence_conflict")
        self.assertEqual(result["diagnostics"]["stages"]["decision"]["status"], "not_reached")

    async def test_parse_schema_error_is_recorded_before_input_clarification(self):
        plan = default_plan().model_copy(update={"task_type": "invalid-task-type"})
        result = await self.workflow(ScriptedModel(plan=plan)).run(USER_INPUT)
        self.assertEqual(result["error"], "lead_output_contract_failed")
        self.assertEqual(result["diagnostics"]["first_failure"]["error"]["category"], "schema_validation_error")
        self.assertEqual(result["researcher_runs"], 0)

    async def test_quote_failure_is_not_conflated_with_schema_failure(self):
        plan = default_plan().model_copy(update={"task_quote": "not present in request"})
        result = await self.workflow(ScriptedModel(plan=plan)).run(USER_INPUT)
        self.assertEqual(result["status"], "clarification_needed")
        error = result["diagnostics"]["stages"]["parse"]["error"]
        self.assertEqual(error["category"], "plan_validation_error")
        self.assertEqual(error["validation_code"], "task_anchor_missing")

    async def test_user_override_survives_deterministic_classification(self):
        plan = default_plan().model_copy(update={"task_type": "reasoning_analysis",
            "user_alpha": StatedNumber(value=.8, source_quote="alpha 0.8")})
        result = await self.workflow(ScriptedModel(plan=plan)).run(USER_INPUT + " alpha 0.8")
        self.assertEqual(result["plan"]["task_type"], "specialized_domain")
        self.assertEqual(result["classification"]["proposed_task_type"], "reasoning_analysis")
        self.assertEqual(result["decision"]["weights"]["alpha"], .8)
        self.assertEqual(result["decision"]["weights"]["weight_mode"], "user_override")

    async def test_metadata_logs_omit_private_input_outputs_and_exception_text(self):
        raw = USER_INPUT + " SIMULATED_PRIVATE_INPUT"
        with self.assertLogs("modelmatch.reliability", level="INFO") as logs:
            result = await self.workflow(WriterFailureModel("provider")).run(raw)
        text = "\n".join(logs.output)
        self.assertIn(result["run_id"], text)
        for private in ("SIMULATED_PRIVATE_INPUT", "SIMULATED_PRIVATE_ERROR", USER_INPUT, "source_quote"):
            self.assertNotIn(private, text)

    async def test_cancellation_records_cancelled_and_unreached_states(self):
        model = ScriptedModel()
        original = model.get_response
        entered = asyncio.Event()
        async def wait(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
            return await original(*args, **kwargs)
        model.get_response = wait
        workflow = self.workflow(model)
        task = asyncio.create_task(workflow.run(USER_INPUT))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(workflow.diagnostics.states["parse"]["status"], "cancelled")
        self.assertEqual(workflow.diagnostics.states["writer"]["status"], "not_reached")


class RuntimeReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_response_without_finish_metadata_remains_unknown(self):
        budget = CallBudget()
        response = SimpleNamespace(usage=Usage(), output=[])
        model = MeteredModel(SimpleNamespace(get_response=AsyncMock(return_value=response)), "gemini-synthetic", budget, VertexConfig("synthetic-project"))
        await model.get_response(None, "synthetic", ModelSettings(), [], None, [], None)
        self.assertIsNone(budget.records[0]["finish_reason"])
        self.assertIsNone(budget.records[0]["model_version"])

    async def test_budget_rejection_and_missing_finish_reason_are_recorded_without_fabrication(self):
        inner = SimpleNamespace(get_response=AsyncMock())
        budget = CallBudget(max_prompt_chars=1)
        model = MeteredModel(inner, "gemini-synthetic", budget, VertexConfig("synthetic-project"))
        with self.assertRaises(BudgetExceeded):
            await model.get_response(None, "private text", ModelSettings(), [], None, [], None)
        self.assertFalse(budget.records[0]["adapter_invoked"])
        self.assertIsNone(budget.records[0]["finish_reason"])
        self.assertEqual(budget.records[0]["failure"]["category"], "budget_exceeded")
        self.assertNotIn("private text", json.dumps(budget.records))
        inner.get_response.assert_not_awaited()

    async def test_call_metadata_uses_task_local_run_context(self):
        response = SimpleNamespace(usage=Usage(input_tokens=2, output_tokens=3), output=[], finish_reason="stop")
        budget = CallBudget()
        model = MeteredModel(SimpleNamespace(get_response=AsyncMock(return_value=response)), "gemini-synthetic", budget, VertexConfig("synthetic-project"))
        async def call(run_id):
            token = CALL_CONTEXT.set({"run_id": run_id, "stage": "writer"})
            try:
                await model.get_response(None, "synthetic", ModelSettings(), [], None, [], None)
            finally:
                CALL_CONTEXT.reset(token)
        await asyncio.gather(call("synthetic-run-a"), call("synthetic-run-b"))
        self.assertEqual({r["run_id"] for r in budget.records}, {"synthetic-run-a", "synthetic-run-b"})
        self.assertTrue(all(r["finish_reason"] == "stop" for r in budget.records))

    async def test_installed_litellm_adapter_retains_raw_finish_metadata(self):
        import litellm
        from agents.extensions.models.litellm_model import LitellmModel
        from agents.models.interface import ModelTracing
        raw = litellm.ModelResponse(id="synthetic-response", model="synthetic-version",
            choices=[{"index": 0, "finish_reason": "length", "message": {"role": "assistant", "content": "{}"}}],
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7,
                   "completion_tokens_details": {"reasoning_tokens": 2}})
        budget = CallBudget()
        with patch.object(LitellmModel, "_fetch_response", new_callable=AsyncMock, return_value=raw):
            model, _ = create_models(VertexConfig("synthetic-project"), budget)
            await model.get_response(None, "synthetic", ModelSettings(), [], None, [], ModelTracing.DISABLED)
        record = budget.records[0]
        self.assertEqual(record["finish_reason"], "length")
        self.assertEqual(record["reported_model"], "synthetic-version")
        self.assertIsNone(record["model_version"])
        self.assertTrue(record["provider_response_received"])
        self.assertEqual(record["reasoning_tokens"], 2)
        self.assertEqual(record["usage"]["total_tokens"], 7)


class HttpRunIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_identity_is_consistent_across_sse_results_and_compatibility_route(self):
        service = web.app.state.modelmatch
        service.saved.clear(); service.recent.clear(); service.active = 0
        with patch.dict(os.environ, {"MODELMATCH_OFFLINE": "1", "MODELMATCH_PUBLIC_ORIGIN": ""}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://local") as client:
                for path in ("/api/modelmatch/analyze", "/run"):
                    response = await client.post(path, json={"question": USER_INPUT}) if path.startswith("/api") else await client.get(path, params={"question": USER_INPUT})
                    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                    run_id = events[0]["run_id"]
                    self.assertEqual(response.headers["X-ModelMatch-Run-ID"], run_id)
                    self.assertTrue(all(e["run_id"] == run_id for e in events))
                    stages = [e for e in events if e["type"] == "stage"]
                    self.assertTrue(all(e["status"] in {"running", "completed", "failed", "skipped", "cancelled"} for e in stages))
                    self.assertTrue(any(e.get("phase_status") == "accepted" and e["status"] == "completed" for e in stages))
                    self.assertEqual(events[-1]["result"]["run_id"], run_id)
                    self.assertTrue(all(e["run_id"] == run_id for e in events[-1]["result"]["trace"]))
