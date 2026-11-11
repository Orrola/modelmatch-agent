"""Offline regressions for actual Gemini stage failures and SDK tool filtering."""

import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents import AgentOutputSchema, RunContextWrapper

from modelmatch_schemas import AgentCallContext, Followup, OrchestrationLimits, ParsedPlan
from orchestration import ModelMatchWorkflow, WorkflowError
from tests.fake_modelmatch import CapturingRunner, ScriptedModel, USER_INPUT, default_plan
from tools.artificial_analysis import load_mock_snapshot

FIXTURE = Path(__file__).parent / "fixtures/lead_parse_failure.json"


class FailureReplayModel(ScriptedModel):
    def __init__(self, failure):
        super().__init__(barrier=False)
        self.failure = failure
        self.fixture = json.loads(FIXTURE.read_text())
        self.seen = []

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **kwargs):
        payload = self.payload(input)
        self.seen.append({"stage": payload.get("stage"), "tools": [t.name for t in tools],
                          "schema": output_schema.json_schema()})
        if payload.get("stage") == "parse":
            if self.failure == "premature_calls":
                return self.tools([(c["name"], c["arguments"]) for c in self.fixture["premature_calls"]])
            return self.text(self.fixture["wrong_stage_output"])
        return await super().get_response(system_instructions, input, model_settings, tools,
                                          output_schema, handoffs, tracing, **kwargs)


class StageControlTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        self.loader = AsyncMock(return_value=self.snapshot)
        self.runner = CapturingRunner()

    def workflow(self, model=None, **kwargs):
        model = model or ScriptedModel()
        return ModelMatchWorkflow(model, model, snapshot_loader=self.loader, runner=self.runner,
            limits=kwargs.pop("limits", OrchestrationLimits(timeout_seconds=10)), **kwargs)

    async def test_actual_premature_calls_are_not_registered_or_executed(self):
        model = FailureReplayModel("premature_calls")
        workflow = self.workflow(model)
        result = await workflow.run(USER_INPUT)
        self.assertEqual(model.seen[0]["tools"], [])
        self.assertEqual(len(model.seen), 1)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "lead_output_contract_failed")
        self.assertEqual(result["researcher_runs"], 0)
        self.assertIsNone(workflow.plan)
        self.assertIsNone(workflow._completed_stage)
        self.loader.assert_not_awaited()
        self.assertFalse(any(e["type"] == "researcher_start" for e in result["trace"]))
        # A response containing tool names is not accepted dispatch or parallel research.
        self.assertTrue(all(b["stage"] == "parse" for b in workflow.batches))

    async def test_actual_wrong_stage_envelope_cannot_become_a_plan(self):
        model = FailureReplayModel("wrong_stage")
        workflow = self.workflow(model)
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["error"], "lead_output_contract_failed")
        self.assertNotIn("stage", model.seen[0]["schema"]["properties"])
        self.assertFalse(model.seen[0]["schema"]["additionalProperties"])
        self.assertIsNone(workflow.plan)
        self.assertEqual(workflow.lead_context.stage, "parse")
        self.assertEqual(result["reviews"], [])
        self.assertEqual(result["researcher_runs"], 0)
        self.loader.assert_not_awaited()

    async def test_model_payload_cannot_override_controller_stage(self):
        model = ScriptedModel()
        workflow = self.workflow(model)
        output = await workflow.lead("parse", {"stage": "review_final", "user_input": USER_INPUT})
        self.assertIsInstance(output, ParsedPlan)
        self.assertEqual(model.model_requests[0]["payload"]["stage"], "parse")
        self.assertEqual(workflow._completed_stage, "parse")

    async def test_stage_schemas_and_sdk_visibility_follow_actual_runs(self):
        task = Followup(role="B", task="Recheck a selected index", reason="Targeted gap review.", model_ids=["synthetic-engineering"])
        model = ScriptedModel(followups=[task])
        workflow = self.workflow(model)
        lead = workflow.team.lead
        context = workflow.lead_context
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        expected = {
            "parse": (set(), "ParsedPlan"),
            "dispatch": ({"research_a", "research_b", "research_c"}, "DispatchComplete"),
            "review": (set(), "Review"),
            "followup": ({"research_b"}, "DispatchComplete"),
            "review_final": (set(), "FinalReview"),
        }
        observed = set()
        for request in model.model_requests:
            stage = request["payload"].get("stage")
            if stage not in expected:
                continue
            observed.add(stage)
            tools, schema_name = expected[stage]
            self.assertEqual(set(request["tools"]), tools)
            self.assertEqual(request["schema_name"], schema_name)
            self.assertNotIn("stage", request["schema"]["properties"])
            self.assertFalse(request["schema"]["additionalProperties"])
            if stage == "review_final":
                self.assertNotIn("followups", request["schema"]["properties"])
            if not tools:
                self.assertFalse(request["parallel_tool_calls"])
        self.assertEqual(observed, set(expected))
        leads = [c for c in self.runner.calls if c["agent"].name == "Lead"]
        self.assertTrue(all(c["agent"] is lead and c["context"] is context for c in leads))
        self.assertEqual(len({c["context"].context_id for c in leads}), 1)
        self.assertEqual([e["stage"] for e in result["trace"] if e["type"] == "lead_stage_completed"],
                         ["parse", "dispatch", "review", "followup", "review_final"])

    async def test_installed_sdk_accepts_every_stage_schema(self):
        from modelmatch_schemas import LEAD_OUTPUT_TYPES
        for output_type in set(LEAD_OUTPUT_TYPES.values()):
            schema = AgentOutputSchema(output_type)
            self.assertTrue(schema.is_strict_json_schema())
            self.assertFalse(schema.json_schema()["additionalProperties"])

    async def test_invalid_initial_transitions_do_not_call_any_model(self):
        for stage in ("dispatch", "review", "followup", "review_final", "unknown"):
            workflow = self.workflow()
            with self.assertRaisesRegex(WorkflowError, "invalid_lead_stage_transition"):
                await workflow.lead(stage, {})
            self.assertEqual(workflow._stage, None)
        self.assertEqual(self.runner.calls, [])

    async def test_repeated_parse_and_missing_prerequisites_are_rejected(self):
        workflow = self.workflow()
        await workflow.lead("parse", {"user_input": USER_INPUT})
        with self.assertRaisesRegex(WorkflowError, "invalid_lead_stage_transition"):
            await workflow.lead("parse", {"user_input": USER_INPUT})
        with self.assertRaisesRegex(WorkflowError, "lead_stage_prerequisites_missing"):
            await workflow.lead("dispatch", {})
        self.assertEqual(len(self.runner.calls), 1)

    async def test_concurrent_lead_stages_cannot_change_shared_agent_schema(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class WaitingModel(ScriptedModel):
            async def get_response(self, *args, **kwargs):
                entered.set()
                await release.wait()
                return await super().get_response(*args, **kwargs)
        workflow = self.workflow(WaitingModel())
        task = asyncio.create_task(workflow.lead("parse", {"user_input": USER_INPUT}))
        await entered.wait()
        original_type = workflow.team.lead.output_type
        with self.assertRaisesRegex(WorkflowError, "invalid_lead_stage_transition"):
            await workflow.lead("dispatch", {})
        self.assertIs(workflow.team.lead.output_type, original_type)
        self.assertEqual(workflow.lead_context.stage, "parse")
        release.set()
        await task

    async def test_sdk_rejects_invalid_contexts_and_closed_workflows(self):
        workflow = self.workflow()
        lead = workflow.team.lead
        for value in (None, {}, SimpleNamespace(role="Lead"),
                      AgentCallContext(workflow, "C", "wrong-role", stage="dispatch"), workflow.lead_context):
            self.assertEqual(await lead.get_all_tools(RunContextWrapper(value)), [])
        await workflow.run(USER_INPUT)
        self.assertEqual(await lead.get_all_tools(RunContextWrapper(workflow.lead_context)), [])
        with self.assertRaisesRegex(WorkflowError, "invalid_lead_stage_transition"):
            await workflow.lead("followup", {})

    async def test_post_call_stage_guards_remain_defense_in_depth(self):
        workflow = self.workflow()
        for role in ("A", "B", "C"):
            with self.assertRaisesRegex(WorkflowError, "research_dispatch_not_allowed"):
                await workflow.launch(role, "Premature research", [])
        self.assertEqual(workflow.researcher_count, 0)

    async def test_followup_dispatch_requires_the_exact_review_authorization(self):
        workflow = self.workflow()
        task = Followup(role="B", task="Unauthorized", reason="Not reviewed.")
        with self.assertRaisesRegex(WorkflowError, "research_dispatch_not_authorized"):
            await workflow._dispatch("followup", [task])
        self.assertEqual(self.runner.calls, [])

    async def test_optional_questions_from_actual_draft_do_not_block_a_valid_task(self):
        fixture = json.loads(FIXTURE.read_text())
        plan = ParsedPlan.model_validate(fixture["wrong_stage_output"]["plan"])
        workflow = self.workflow(ScriptedModel(plan=plan))
        result = await workflow.run(fixture["user_input"])
        self.assertEqual(result["status"], "supported", result.get("error"))
        self.assertEqual(result["researcher_runs"], 3)
        self.assertEqual(len(result["clarification_suggestions"]), 4)
        self.assertEqual(workflow.requirements, ())
        self.assertTrue(all(value is None for value in result["plan"]["workload"].values()))
        self.loader.assert_awaited_once()

    async def test_only_requested_monthly_cost_requires_workload_clarification(self):
        from modelmatch_schemas import ParsedConstraint
        plan = default_plan()
        plan.constraints = [ParsedConstraint(metric="monthly_cost_usd", target=100, source_quote="budget $100")]
        plan.clarification_questions = ["What latency would you prefer?"]
        result = await self.workflow(ScriptedModel(plan=plan)).run(USER_INPUT + " budget $100")
        self.assertEqual(result["status"], "clarification_needed")
        self.assertEqual(len(result["questions"]), 1)
        self.assertIn("Monthly cost requires", result["questions"][0])
        self.assertNotIn("latency", result["questions"][0])
        self.loader.assert_not_awaited()

    async def test_industry_only_request_still_requires_a_concrete_task(self):
        plan = default_plan().model_copy(update={"industry": "Finance", "task_description": "Finance", "task_quote": "Finance"})
        result = await self.workflow(ScriptedModel(plan=plan)).run("Finance")
        self.assertEqual(result["status"], "clarification_needed")
        self.loader.assert_not_awaited()

    async def test_zero_followup_budget_cannot_execute_requested_research(self):
        task = Followup(role="B", task="Recheck U", reason="Missing U.")
        result = await self.workflow(ScriptedModel(followups=[task]),
                                    limits=OrchestrationLimits(max_followup_rounds=0)).run(USER_INPUT)
        self.assertEqual(result["researcher_runs"], 3)
        self.assertTrue(any(e.get("reason") == "followup_round_limit" for e in result["trace"]))
