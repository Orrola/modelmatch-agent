"""Real SDK orchestration driven by an offline, deterministic scripted model."""

import asyncio
import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from context_panel import AgentContexts, PanelHooks
from modelmatch_schemas import (
    Followup, OrchestrationLimits, ParsedConstraint, ParsedWorkload, StatedNumber,
)
from orchestration import ModelMatchWorkflow
from tests.fake_modelmatch import CapturingRunner, ScriptedModel, USER_INPUT, default_plan
from tests.test_official_specs import EXCERPT, URL, FixtureGrounding
from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide
from tools.model_evidence import RelevanceDecision, build_candidates


class OrchestrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        self.events = []
        self.contexts = AgentContexts()
        self.panel = PanelHooks(self.contexts, self.events.append)
        self.loader = AsyncMock(return_value=self.snapshot)
        self.runner = CapturingRunner()

    def workflow(self, model=None, **kwargs):
        model = model or ScriptedModel()
        return ModelMatchWorkflow(model, model, hooks=self.panel, snapshot_loader=self.loader,
            runner=self.runner, limits=kwargs.pop("limits", OrchestrationLimits(timeout_seconds=10)), **kwargs)

    async def test_full_flow_uses_real_sdk_shared_snapshot_and_same_lead(self):
        model = ScriptedModel()
        workflow = self.workflow(model)
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        self.loader.assert_awaited_once()
        leads = [call for call in self.runner.calls if call["agent"].name == "Lead"]
        self.assertEqual(len(leads), 3)
        self.assertTrue(all(call["agent"] is workflow.team.lead and call["context"] is workflow.lead_context for call in leads))
        self.assertTrue(all(len(call["input"]) > len(leads[0]["input"]) for call in leads[1:]))
        self.assertIn("decision_completed", [e["type"] for e in result["trace"]])
        expected = decide(workflow.prepared(), task_type="specialized_domain")
        self.assertEqual(result["decision"], expected)
        self.assertIn("Data: [Artificial Analysis]", result["markdown"])
        self.assertIn("Offline synthetic test output", result["markdown"])

    async def test_fresh_contexts_and_actual_parallel_execution(self):
        model = ScriptedModel(barrier=True)
        workflow = self.workflow(model)
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        researchers = [call for call in self.runner.calls if call["agent"].name.startswith("Researcher")]
        self.assertEqual(len(researchers), 3)
        self.assertEqual(len({id(call["context"]) for call in researchers}), 3)
        self.assertEqual(len({call["context"].context_id for call in researchers}), 3)
        self.assertTrue(all(isinstance(call["input"], str) for call in researchers))
        self.assertTrue(all(call["context"] is not workflow.lead_context for call in researchers))
        self.assertTrue(all(call["context"].coordinator.snapshot is self.snapshot for call in researchers))
        self.assertTrue(model.barrier.is_set())
        starts = [e["monotonic"] for e in result["trace"] if e["type"] == "researcher_start"]
        ends = [e["monotonic"] for e in result["trace"] if e["type"] == "researcher_end"]
        self.assertLess(max(starts), min(ends))
        self.assertTrue(any(set(b["calls"]) == {"research_a", "research_b", "research_c"} for b in workflow.batches))
        self.assertTrue(any(name.startswith("Researcher A") for name in self.contexts.contexts))

    async def test_final_decision_runs_once_after_lead_review(self):
        workflow = self.workflow()
        with patch("orchestration.decide", wraps=decide) as decision:
            result = await workflow.run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        decision.assert_called_once()
        review = next(e["seq"] for e in result["trace"] if e["type"] == "evidence_review")
        decision_start = next(e["seq"] for e in result["trace"] if e["type"] == "decision_started")
        self.assertLess(review, decision_start)

    async def test_targeted_followup_then_same_lead_review(self):
        task = Followup(role="B", task="Recheck missing domain evidence", reason="Inspect the unresolved selected-domain score.", model_ids=["synthetic-engineering"])
        workflow = self.workflow(ScriptedModel(followups=[task]))
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        starts = [e for e in result["trace"] if e["type"] == "researcher_start"]
        self.assertEqual([e["role"] for e in starts].count("B"), 2)
        self.assertEqual(starts[-1]["model_ids"], ["synthetic-engineering"])
        self.assertEqual([r["stage"] for r in result["reviews"]], ["review", "review_final"])
        self.assertEqual(result["researcher_runs"], 4)
        self.assertIsNone(result["decision"]["candidates"]["synthetic-engineering"]["U"])

    async def test_followup_cap_even_when_lead_requests_more(self):
        tasks = [Followup(role=role, task=f"Retry {role}", reason="Targeted review of unresolved evidence.") for role in ("A", "B", "C")]
        result = await self.workflow(ScriptedModel(followups=tasks, repeat_followups=True)).run(USER_INPUT)
        self.assertEqual(result["researcher_runs"], 6)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "lead_output_contract_failed")

    async def test_missing_u_not_filled_or_ignored(self):
        result = await self.workflow().run(USER_INPUT)
        candidate = result["decision"]["candidates"]["synthetic-engineering"]
        self.assertIsNone(candidate["U"])
        self.assertIsNone(candidate["S"])
        self.assertEqual(candidate["candidate_status"], "provisional")
        b = result["researcher_results"]["B"]
        self.assertTrue(b["missing_manifest"])
        self.assertTrue(all(e["evidence_status"] == "observed" for e in b["valid_evidence"].values()))

    async def test_unsupported_domain_has_no_numeric_recommendation(self):
        result = await self.workflow(ScriptedModel(domain=None, match_status="none")).run(USER_INPUT)
        self.assertEqual(result["status"], "not_supported")
        self.assertEqual(result["decision"]["rankings"]["fully_evaluable"], [])
        self.assertIn("No reliable numeric recommendation", result["markdown"])

    async def test_partial_domain_stays_provisional(self):
        result = await self.workflow(ScriptedModel(match_status="partial")).run(USER_INPUT)
        self.assertEqual(result["status"], "provisional")
        self.assertIn("Provisional shortlist", result["markdown"])

    async def test_unclear_request_clarifies_before_data_access(self):
        plan = default_plan().model_copy(update={"task_description": "Best LLM", "task_quote": "Best LLM"})
        result = await self.workflow(ScriptedModel(plan=plan)).run("Best LLM?")
        self.assertEqual(result["status"], "clarification_needed")
        self.loader.assert_not_awaited()
        self.assertEqual(result["researcher_runs"], 0)

    async def test_invented_hard_constraint_rejected(self):
        plan = default_plan()
        plan.constraints = [ParsedConstraint(metric="ttft", target=1, hard=True, source_quote="Analyze financial documents")]
        result = await self.workflow(ScriptedModel(plan=plan)).run(USER_INPUT)
        self.assertEqual(result["status"], "clarification_needed")
        self.loader.assert_not_awaited()

    async def test_monthly_budget_without_workload_clarifies(self):
        plan = default_plan()
        plan.constraints = [ParsedConstraint(metric="monthly_cost_usd", target=100, source_quote="budget $100")]
        result = await self.workflow(ScriptedModel(plan=plan)).run(USER_INPUT + " budget $100")
        self.assertEqual(result["status"], "clarification_needed")
        self.loader.assert_not_awaited()

    async def test_unknown_context_constraint_remains_unverified(self):
        plan = default_plan()
        plan.constraints = [ParsedConstraint(metric="context_window", target=100000, hard=True,
            source_quote="must support 100000 context tokens", hard_source_quote="must support 100000 context tokens")]
        result = await self.workflow(ScriptedModel(plan=plan)).run(USER_INPUT + " must support 100000 context tokens")
        self.assertEqual(result["status"], "not_supported", result.get("error"))
        self.assertTrue(all(c["candidate_status"] == "unverified" for c in result["decision"]["candidates"].values()))

    async def test_optional_grounding_service_resolves_only_verified_candidate(self):
        from tools.official_specs import OfficialSpecService
        plan = default_plan()
        quote = "must support 50000 context tokens"
        plan.constraints = [ParsedConstraint(metric="context_window", target=50000, hard=True,
                                              source_quote=quote, hard_source_quote=quote)]
        row = self.snapshot["pages"][0]["data"][0]
        row["slug"] = "gemini-test-001"
        row["model_creator"]["name"] = "Google"
        fetcher = AsyncMock(return_value={"url": URL, "text": EXCERPT, "source_date": datetime.now(timezone.utc).date().isoformat()})
        service = OfficialSpecService(FixtureGrounding(), fetcher=fetcher, max_candidates=1, max_grounding_calls=1)
        workflow = self.workflow(ScriptedModel(plan=plan), official_service=service)
        result = await workflow.run(USER_INPUT + " " + quote)
        self.assertEqual(result["status"], "supported", result.get("error"))
        self.assertEqual(result["decision"]["candidates"]["synthetic-finance"]["eligibility"], "eligible")
        self.assertEqual(result["decision"]["candidates"]["synthetic-engineering"]["eligibility"], "unverified")
        self.assertEqual(service.calls, 1)
        self.assertTrue(result["official_specifications"])

    async def test_explicit_weight_override_preserved_through_research(self):
        plan = default_plan()
        plan.user_alpha = StatedNumber(value=0.6, source_quote="60%")
        result = await self.workflow(ScriptedModel(plan=plan)).run(USER_INPUT + " general weight 60%")
        self.assertEqual(result["decision"]["weights"]["alpha"], 0.6)
        self.assertEqual(result["decision"]["weights"]["weight_mode"], "user_override")

    async def test_explicit_workload_uses_existing_cost_and_penalty_rules(self):
        plan = default_plan()
        plan.constraints = [ParsedConstraint(metric="monthly_cost_usd", target=2, source_quote="soft budget $2")]
        plan.workload = ParsedWorkload(
            monthly_requests=StatedNumber(value=1000, source_quote="1000 requests"),
            avg_input_tokens=StatedNumber(value=1000, source_quote="1000 input tokens"),
            avg_output_tokens=StatedNumber(value=1000, source_quote="1000 output tokens"))
        text = USER_INPUT + " soft budget $2; 1000 requests monthly, averaging 1000 input tokens and 1000 output tokens"
        result = await self.workflow(ScriptedModel(plan=plan)).run(text)
        candidate = result["decision"]["candidates"]["synthetic-finance"]
        self.assertEqual(candidate["estimated_monthly_cost_usd"], 3)
        self.assertEqual(candidate["O"], -4)
        self.assertEqual(candidate["S"], 23)
        self.assertEqual(result["researcher_results"]["C"]["operations"]["synthetic-finance"]["O"], -4)

    async def test_targeted_c_followup_preserves_other_model_operations(self):
        task = Followup(role="C", task="Recheck one model's operations", reason="Review available operational evidence.", model_ids=["synthetic-finance"])
        result = await self.workflow(ScriptedModel(followups=[task])).run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        self.assertEqual(len(result["researcher_results"]["C"]["operations"]), 5)

    async def test_researcher_failure_stops_recommendation_and_redacts_exception(self):
        result = await self.workflow(ScriptedModel(fail_roles=["A"])).run(USER_INPUT)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertNotIn("decision", result)
        self.assertNotIn("SIMULATED_SECRET", json.dumps(result))
        self.assertNotIn("SIMULATED_SECRET", json.dumps(self.contexts.events))

    async def test_targeted_retry_can_recover_failed_researcher(self):
        task = Followup(role="A", task="Retry General data access", reason="Transient researcher failure.")
        result = await self.workflow(ScriptedModel(fail_once_roles=["A"], followups=[task])).run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        self.assertEqual(result["researcher_runs"], 4)

    async def test_data_tool_error_is_not_secret_or_fake_evidence(self):
        workflow = self.workflow()
        original = workflow.retrieve
        def broken(context, role, *args):
            if role == "A":
                raise RuntimeError("SIMULATED_SECRET_MUST_NOT_ESCAPE")
            return original(context, role, *args)
        workflow.retrieve = broken
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertNotIn("SIMULATED_SECRET", json.dumps(result))

    async def test_data_calls_are_bounded(self):
        result = await self.workflow(ScriptedModel(data_call_count=3)).run(USER_INPUT)
        self.assertEqual(result["status"], "insufficient_evidence")
        ends = [e for e in result["trace"] if e["type"] == "researcher_end"]
        self.assertTrue(all(e["data_calls"] == 2 for e in ends))

    async def test_duplicate_root_dispatch_cannot_start_extra_researcher(self):
        result = await self.workflow(ScriptedModel(duplicate_dispatch=True)).run(USER_INPUT)
        self.assertLessEqual(result["researcher_runs"], 3)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "researchers_not_dispatched_in_one_model_turn")

    async def test_sequential_dispatch_does_not_claim_parallel_compliance(self):
        result = await self.workflow(ScriptedModel(sequential_dispatch=True, barrier=False)).run(USER_INPUT)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "researchers_not_dispatched_in_one_model_turn")

    async def test_writer_cannot_override_candidates(self):
        result = await self.workflow(ScriptedModel(writer_tamper=True)).run(USER_INPUT)
        self.assertTrue(result["writer_fallback"])
        self.assertNotIn("invented-model", result["markdown"])
        self.assertIn("Top candidates", result["markdown"])

    async def test_skipping_data_tool_does_not_create_evidence(self):
        result = await self.workflow(ScriptedModel(skip_data=True)).run(USER_INPUT)
        self.assertEqual(result["status"], "insufficient_evidence")

    async def test_snapshot_error_is_safe(self):
        self.loader.side_effect = RuntimeError("SIMULATED_SECRET_MUST_NOT_ESCAPE")
        result = await self.workflow().run(USER_INPUT)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "snapshot_unavailable")
        self.assertNotIn("SIMULATED_SECRET", json.dumps(result))

    async def test_invalid_followup_scope_is_rejected(self):
        task = Followup(role="B", task="Look up unrelated model", reason="Invalid test scope", model_ids=["not-an-aa-id"])
        result = await self.workflow(ScriptedModel(followups=[task])).run(USER_INPUT)
        self.assertEqual(result["status"], "error")
        self.assertLessEqual(result["researcher_runs"], 3)

    async def test_limits_and_single_request_lifecycle(self):
        with self.assertRaises(ValueError):
            OrchestrationLimits(max_followup_rounds=2)
        workflow = self.workflow()
        await workflow.run(USER_INPUT)
        with self.assertRaises(ValueError):
            await workflow.run(USER_INPUT)

    async def test_workflow_deadline_is_bounded(self):
        async def waiting_snapshot():
            await asyncio.Event().wait()
        workflow = self.workflow(limits=OrchestrationLimits(timeout_seconds=0.1))
        workflow.snapshot_loader = waiting_snapshot
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["error"], "workflow_timeout")

    async def test_cancellation_propagates_without_a_recommendation(self):
        started = asyncio.Event()
        async def waiting_snapshot():
            started.set()
            await asyncio.Event().wait()
        workflow = self.workflow()
        workflow.snapshot_loader = waiting_snapshot
        task = asyncio.create_task(workflow.run(USER_INPUT))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(workflow.trace[-1]["type"], "workflow_cancelled")

    async def test_missing_and_invalid_model_ids_never_join_by_position(self):
        broken = copy.deepcopy(self.snapshot)
        broken["pages"][0]["data"][1]["id"] = broken["pages"][0]["data"][0]["id"]
        self.loader.return_value = broken
        result = await self.workflow().run(USER_INPUT)
        self.assertEqual(result["error"], "snapshot_unavailable")
        self.assertEqual(result["researcher_runs"], 0)
