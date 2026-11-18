"""Initial dispatch completion through the real offline Agents SDK Runner."""

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from modelmatch_schemas import Followup, OrchestrationLimits
from orchestration import ModelMatchWorkflow
from tests.fake_modelmatch import CapturingRunner, ScriptedModel, USER_INPUT
from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide


class NoAcknowledgmentModel(ScriptedModel):
    async def get_response(self, system_instructions, input, *args, **kwargs):
        payload = self.payload(input)
        if payload.get("stage") == "dispatch" and self.counts.get(("Lead", "dispatch"), 0):
            raise AssertionError("An unnecessary dispatch confirmation generation was attempted.")
        return await super().get_response(system_instructions, input, *args, **kwargs)


class InvalidBatchModel(ScriptedModel):
    def __init__(self, mode):
        super().__init__(barrier=False)
        self.mode = mode

    async def get_response(self, system_instructions, input, *args, **kwargs):
        response = await super().get_response(system_instructions, input, *args, **kwargs)
        if self.payload(input).get("stage") == "dispatch":
            if self.mode == "missing":
                response.output.pop()
            elif self.mode == "unauthorized":
                response.output[0].name = "research_d"
            elif self.mode == "scope":
                response.output[0].arguments = json.dumps({"task": "Inspect evidence", "model_ids": ["not-authorized"]})
        return response


class DispatchCompletionTests(unittest.IsolatedAsyncioTestCase):
    def workflow(self, model):
        snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        return ModelMatchWorkflow(model, model, snapshot_loader=AsyncMock(return_value=snapshot),
            runner=CapturingRunner(), limits=OrchestrationLimits(timeout_seconds=10))

    async def test_success_avoids_confirmation_but_preserves_same_lead_review_and_ranking(self):
        model = NoAcknowledgmentModel()
        workflow = self.workflow(model)
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        self.assertEqual(model.counts[("Lead", "dispatch")], 1)
        self.assertEqual(model.counts[("Lead", "review")], 1)
        self.assertEqual(result["decision"], decide(workflow.prepared(), task_type="specialized_domain"))
        self.assertFalse(result["writer_fallback"])
        self.assertEqual(result["diagnostics"]["stages"]["dispatch"]["status"], "accepted")
        leads = [c for c in workflow.runner.calls if c["agent"] is workflow.team.lead]
        self.assertEqual([c["stage"] for c in leads], ["parse", "dispatch", "review"])
        self.assertTrue(all(c["context"] is workflow.lead_context for c in leads))
        review = leads[-1]["input"]
        self.assertEqual(sum(item.get("type") == "function_call_output" for item in review), 3)
        self.assertEqual(workflow.team.lead.tool_use_behavior, "run_llm_again")
        starts = [e for e in result["trace"] if e["type"] == "researcher_start"]
        ends = [e for e in result["trace"] if e["type"] == "researcher_end"]
        self.assertEqual(len({e["context_id"] for e in starts}), 3)
        self.assertLess(max(e["monotonic"] for e in starts), min(e["monotonic"] for e in ends))
        self.assertTrue(model.barrier.is_set())

    async def test_missing_duplicate_split_and_unauthorized_batches_are_rejected_before_tools(self):
        models = [InvalidBatchModel("missing"), InvalidBatchModel("unauthorized"),
                  ScriptedModel(duplicate_dispatch=True, barrier=False),
                  ScriptedModel(sequential_dispatch=True, barrier=False)]
        for model in models:
            with self.subTest(model=type(model).__name__):
                workflow = self.workflow(model)
                result = await workflow.run(USER_INPUT)
                self.assertEqual(result["error"], "researchers_not_dispatched_in_one_model_turn")
                self.assertEqual(result["researcher_runs"], 0)
                self.assertEqual(result["diagnostics"]["stages"]["parse"]["status"], "accepted")
                self.assertEqual(result["diagnostics"]["stages"]["dispatch"]["status"], "failed")
                self.assertEqual(workflow.team.lead.tool_use_behavior, "run_llm_again")

    async def test_expanded_scope_is_rejected_without_starting_research(self):
        result = await self.workflow(InvalidBatchModel("scope")).run(USER_INPUT)
        self.assertEqual(result["error"], "research_dispatch_not_authorized")
        self.assertEqual(result["researcher_runs"], 0)

    async def test_malformed_failed_or_incomplete_result_cannot_complete_callback(self):
        for mode in ("malformed", "failed", "count", "snapshot", "payload"):
            with self.subTest(mode=mode):
                workflow = self.workflow(ScriptedModel())
                launch = workflow.launch

                async def altered(role, task, ids):
                    raw = await launch(role, task, ids)
                    if role != "A":
                        return raw
                    if mode == "malformed":
                        return "incomplete-json"
                    if mode == "snapshot":
                        workflow.role_results[role]["snapshot_id"] = "wrong-snapshot"
                    if mode == "payload":
                        workflow.role_results[role]["models"].pop(next(iter(workflow.role_results[role]["models"])))
                    value = json.loads(raw)
                    if mode == "failed":
                        value["status"] = "failed"
                    if mode == "count":
                        value["model_count"] = True
                    return json.dumps(value)

                workflow.launch = altered
                result = await workflow.run(USER_INPUT)
                self.assertEqual(result["error"], "initial_dispatch_result_invalid")
                self.assertNotIn("decision", result)
                self.assertFalse(any(e["type"] == "dispatch_completion_validated" for e in result["trace"]))

    async def test_explicit_researcher_failure_keeps_existing_review_and_authorized_recovery(self):
        task = Followup(role="A", task="Recheck General evidence", reason="Inspect the failed role.", model_ids=[])
        model = ScriptedModel(fail_once_roles=["A"], followups=[task])
        workflow = self.workflow(model)
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        self.assertTrue(any(e["type"] == "dispatch_completion_deferred" for e in result["trace"]))
        self.assertFalse(any(e["type"] == "dispatch_completion_validated" for e in result["trace"]))
        self.assertEqual(model.counts[("Lead", "dispatch")], 2)
        self.assertEqual([r["stage"] for r in result["reviews"]], ["review", "review_final"])

    async def test_successful_initial_batch_does_not_change_controller_followup(self):
        task = Followup(role="B", task="Inspect missing domain evidence", reason="Review the remaining gap.",
                        model_ids=["synthetic-engineering"])
        model = NoAcknowledgmentModel(followups=[task])
        workflow = self.workflow(model)
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        self.assertEqual(model.counts[("Lead", "dispatch")], 1)
        self.assertNotIn(("Lead", "followup"), model.counts)
        self.assertEqual(model.counts[("Lead", "review_final")], 1)
        self.assertEqual(result["researcher_runs"], 4)
        self.assertEqual(workflow.batches[-1]["source"], "controller")
