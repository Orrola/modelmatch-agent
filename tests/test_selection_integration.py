"""Canonical selection, frozen sessions and strict Writer integration without providers."""

import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from modelmatch_schemas import OrchestrationLimits, ParsedConstraint, ParsedWorkload, StatedNumber, WriterOutput
from orchestration import ModelMatchWorkflow
from recommendation import render_recommendation, validate_writer, writer_payload
from tests import test_recommendation_selector as selector_tests
from tests.fake_modelmatch import CapturingRunner, ScriptedModel, USER_INPUT, default_plan
from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide
from tools.model_evidence import OperationalRequirement, RelevanceDecision, Workload, build_candidates
from tools.model_metadata import build_identity_sidecar
from tools.recommendation_selector import select_recommendations
from tools.selection_pipeline import selection_for_decision


def synthetic_inputs(*, specs=None, cost=True, requirements=None):
    case = selector_tests.SelectorTests()
    case.setUp()
    if specs is not None:
        case.specs = specs
    with patch.object(selector_tests, "build_identity_sidecar", wraps=build_identity_sidecar) as builder:
        decision, metadata, coverage = case.inputs(cost=cost, requirements=requirements)
    mapping = builder.call_args.kwargs["mapping"]
    req = ([OperationalRequirement("monthly_cost_usd")] if cost else []) if requirements is None else requirements
    prepared = build_candidates(case.snapshot, RelevanceDecision("Synthetic task", "finance", "strong", "Synthetic task proxy only."),
        req, workload=Workload(1, 1000000, 1000000), shortlist_size=1)
    return decision, metadata, coverage, case.snapshot, prepared, mapping


class CanonicalContractTests(unittest.TestCase):
    def test_zero_one_two_three_slots_preserve_complete_evidence_and_render_order(self):
        cases = [
            (0, dict(requirements=[OperationalRequirement("context_window", 100000, hard=True)])),
            (1, dict(specs=[("a", 90, 100, "A", None)])),
            (2, dict(cost=False)),
            (3, {}),
        ]
        for expected, values in cases:
            with self.subTest(count=expected):
                decision, metadata, coverage, *_ = synthetic_inputs(**values)
                selection = select_recommendations(decision, metadata, coverage)
                before = deepcopy(decision)
                payload = writer_payload(decision, selection)
                ids = [s["candidate"]["model_id"] for s in selection["slots"].values() if s["candidate"]]
                self.assertEqual(payload["candidate_ids"], ids)
                self.assertEqual(len(ids), expected)
                evidence = sorted({e for mid in ids for e in decision["candidates"][mid]["evidence_ids"]
                    if decision["evidence"][e]["evidence_status"] == "observed"})
                self.assertEqual(payload["evidence_ids"], evidence)
                intent = WriterOutput(candidate_ids=ids, evidence_ids=evidence, validation_steps=["task_pilot"])
                validate_writer(intent, payload)
                report = render_recommendation(decision, intent, selection)
                self.assertIn(selection["selection_id"], report)
                self.assertEqual(decision, before)
                self.assertEqual(payload["status"] == "not_supported", expected == 0)

    def test_canonical_roles_differ_from_raw_top_three_and_writer_cannot_reorder(self):
        decision, metadata, coverage, *_ = synthetic_inputs()
        selection = select_recommendations(decision, metadata, coverage)
        payload = writer_payload(decision, selection)
        self.assertEqual(payload["candidate_ids"], ["a", "c", "d"])
        self.assertEqual([r["model_id"] for r in decision["rankings"]["fully_evaluable"][:3]], ["a", "b", "c"])
        for ids, evidence in ((["a", "b", "c"], payload["evidence_ids"]),
                              (["d", "c", "a"], payload["evidence_ids"]),
                              (payload["candidate_ids"], payload["evidence_ids"][:-1]),
                              (payload["candidate_ids"], payload["evidence_ids"] + ["invented"])):
            with self.assertRaises(ValueError):
                validate_writer(WriterOutput(candidate_ids=ids, evidence_ids=evidence, validation_steps=["task_pilot"]), payload)
        altered = deepcopy(selection)
        altered["slots"]["best_overall"]["candidate"]["S"] += 1
        with self.assertRaises(ValueError):
            writer_payload(decision, altered)

    def test_frozen_context_reused_without_mapping_reload_and_deterministic_identity(self):
        decision, _, _, snapshot, prepared, mapping = synthetic_inputs()
        with patch("tools.selection_pipeline.load_family_mapping", return_value=mapping):
            original, context = selection_for_decision(decision, prepared, snapshot=snapshot)
        self.assertEqual(original["selector"]["status"], "limited_metadata")
        self.assertEqual(context["metadata"]["mapping_version"], mapping["version"])
        with patch("tools.selection_pipeline.load_family_mapping", side_effect=AssertionError("No mapping reload")):
            repeated, same_context = selection_for_decision(decision, prepared, frozen_context=context)
            self.assertEqual(original, repeated)
            self.assertIs(same_context, context)
            updated = decide(prepared, user_alpha=.7)
            changed, _ = selection_for_decision(updated, prepared, frozen_context=context)
        self.assertNotEqual(changed["selection"]["selection_id"], original["selection"]["selection_id"])
        self.assertEqual(changed["selection"]["mapping_version"], mapping["version"])

    def test_snapshot_mapping_policy_and_metadata_mismatch_are_independent_failures(self):
        decision, _, _, snapshot, prepared, mapping = synthetic_inputs()
        with patch("tools.selection_pipeline.load_family_mapping", return_value=mapping):
            original, context = selection_for_decision(decision, prepared, snapshot=snapshot)
        for field in ("snapshot", "mapping", "policy", "metadata"):
            altered = deepcopy(context)
            if field == "snapshot":
                altered["snapshot"]["snapshot_id"] = "other-snapshot"
            elif field == "mapping":
                altered["family_mapping"]["version"] = "other-mapping"
            elif field == "policy":
                altered["selector_version"] = "other-policy"
            else:
                altered["metadata"]["models"]["a"]["original_name"] = "Changed identity"
            with self.subTest(field=field):
                before = deepcopy(decision)
                result, _ = selection_for_decision(decision, prepared, frozen_context=altered)
                self.assertEqual(result["selector"]["status"], "unavailable")
                self.assertIsNone(result["selection"])
                self.assertEqual(before, decision)
        result, _ = selection_for_decision(decision, prepared)
        self.assertEqual(result["selector"]["error"]["code"], "selector_context_incompatible")

    def test_saved_session_isolated_from_mutation_of_prepared_and_metadata(self):
        from modelmatch_web import AnalysisService
        decision, _, _, snapshot, prepared, mapping = synthetic_inputs()
        with patch("tools.selection_pipeline.load_family_mapping", return_value=mapping):
            fields, context = selection_for_decision(decision, prepared, snapshot=snapshot)
        service = AnalysisService()
        key = service.remember({"decision": decision, **fields}, prepared, context)
        frozen = deepcopy(service.saved[key])
        prepared.clear()
        context["metadata"].clear()
        fields["selection"].clear()
        self.assertEqual(service.saved[key], frozen)


class WorkflowSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def run_workflow(self, model=None, snapshot=None, question=USER_INPUT):
        snapshot = snapshot or load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        model = model or ScriptedModel()
        runner = CapturingRunner()
        workflow = ModelMatchWorkflow(model, model, runner=runner, snapshot_loader=AsyncMock(return_value=snapshot),
            limits=OrchestrationLimits(timeout_seconds=10))
        return await workflow.run(question), workflow, runner

    async def test_real_sdk_writer_receives_canonical_order_same_lead_and_raw_decision(self):
        _, _, _, snapshot, _, mapping = synthetic_inputs(cost=False)
        with patch("tools.selection_pipeline.load_family_mapping", return_value=mapping):
            result, workflow, runner = await self.run_workflow(snapshot=snapshot)
        self.assertEqual(result["writer_status"], "accepted", result.get("error"))
        payload = writer_payload(result["decision"], result["selection"])
        self.assertEqual(payload["candidate_ids"], ["a", "c"])
        writer = next(c for c in runner.calls if c["agent"].name == "Writer")
        self.assertEqual(json.loads(writer["input"])["candidate_ids"], payload["candidate_ids"])
        self.assertEqual(result["decision"], decide(workflow.prepared(), task_type="specialized_domain"))
        leads = [c for c in runner.calls if c["agent"].name == "Lead"]
        self.assertTrue(all(c["agent"] is workflow.team.lead and c["context"] is workflow.lead_context for c in leads))
        researchers = [c for c in runner.calls if c["agent"].name.startswith("Researcher")]
        self.assertEqual(len({c["context"].context_id for c in researchers}), 3)
        self.assertEqual(len({c["context"].context_id for c in researchers} & {workflow.lead_context.context_id}), 0)

    async def test_three_role_strict_writer_generation_and_frozen_complete_metadata(self):
        specs = [("a", 90, 100, "A", "fa"), ("b", 89, 90, "A", "fa"),
                 ("c", 88, 50, "B", "fb"), ("d", 87, 40, "C", "fc")]
        _, _, _, snapshot, _, mapping = synthetic_inputs(specs=specs)
        plan = default_plan()
        plan.workload = ParsedWorkload(
            monthly_requests=StatedNumber(value=1, source_quote="Monthly requests 1"),
            avg_input_tokens=StatedNumber(value=1000000, source_quote="average input tokens 1000000"),
            avg_output_tokens=StatedNumber(value=1000000, source_quote="average output tokens 1000000"))
        plan.constraints = [ParsedConstraint(metric="monthly_cost_usd", target=10000,
            source_quote="soft monthly budget 10000")]
        question = USER_INPUT + " Monthly requests 1; average input tokens 1000000; average output tokens 1000000; soft monthly budget 10000."
        with patch("tools.selection_pipeline.load_family_mapping", return_value=mapping):
            result, _, runner = await self.run_workflow(ScriptedModel(plan=plan), snapshot, question)
        self.assertEqual(result["selector"]["status"], "available", result.get("error"))
        self.assertEqual(result["writer_status"], "accepted")
        payload = json.loads(next(c["input"] for c in runner.calls if c["agent"].name == "Writer"))
        self.assertEqual(payload["candidate_ids"], ["a", "c", "d"])
        self.assertEqual(payload["selection_id"], result["selection"]["selection_id"])
        self.assertNotIn("potential_alternatives", payload)

    async def test_selector_failure_preserves_raw_decision_and_skips_writer_truthfully(self):
        with patch("tools.selection_pipeline.select_recommendations", side_effect=RuntimeError("PRIVATE_FAILURE_BODY")):
            result, workflow, runner = await self.run_workflow()
        self.assertEqual(result["selector"]["status"], "unavailable")
        self.assertEqual(result["writer_status"], "skipped")
        self.assertFalse(result["writer_fallback"])
        self.assertTrue(result["report_fallback"])
        self.assertFalse(any(c["agent"].name == "Writer" for c in runner.calls))
        self.assertEqual(result["diagnostics"]["stages"]["writer"]["status"], "skipped")
        self.assertEqual(result["decision"], decide(workflow.prepared(), task_type="specialized_domain"))
        self.assertIn("not a verified decision-oriented recommendation", result["markdown"])
        self.assertNotIn("PRIVATE_FAILURE_BODY", json.dumps(result))

    async def test_writer_failure_fallback_preserves_same_canonical_selection(self):
        from tests.test_production_reliability import WriterFailureModel
        result, _, _ = await self.run_workflow(WriterFailureModel("omit_evidence"))
        self.assertTrue(result["writer_fallback"])
        self.assertEqual(result["writer_status"], "fallback")
        self.assertEqual(result["writer_error"]["validation_code"], "evidence_set_mismatch")
        payload = writer_payload(result["decision"], result["selection"])
        self.assertTrue(all(f"`{eid}`" in result["markdown"] for eid in payload["evidence_ids"]))


class SelectionHttpTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import app
        self.app = app.app
        self.service = self.app.state.modelmatch
        self.service.saved.clear()
        self.service.recent.clear()
        self.service.active = 0
        from tools.chat_sessions import ChatSessionStore
        self.service.chat_sessions = ChatSessionStore()
        mode = patch.dict(os.environ, {"MODELMATCH_OFFLINE": "1", "MODELMATCH_CHAT_EVALUATION_ENABLED": "1"})
        mode.start()
        self.addCleanup(mode.stop)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://offline-test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def analysis(self, **fields):
        response = await self.client.post("/api/modelmatch/analyze", json={"question": USER_INPUT, **fields})
        events = [json.loads(s[6:]) for s in response.text.splitlines() if s.startswith("data: ")]
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(any(e["type"] == "stage" for e in events))
        return events[-1]

    async def test_recalculate_reuses_private_frozen_context_with_no_models_or_snapshot_fetch(self):
        done = await self.analysis(user_alpha=.5)
        key = done["analysis_id"]
        saved = deepcopy(self.service.saved[key])
        with patch.object(self.service, "run", side_effect=AssertionError("No research rerun")), \
             patch("tools.artificial_analysis.ArtificialAnalysisClient.fetch_snapshot", side_effect=AssertionError("No AA fetch")), \
             patch("tools.selection_pipeline.load_family_mapping", side_effect=AssertionError("No mapping reload")), \
             patch("vertex_runtime.create_models", side_effect=AssertionError("No provider creation")):
            same = (await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": key, "user_alpha": .5})).json()
            changed = (await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": key, "user_alpha": .7})).json()
            reset = (await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": key, "user_alpha": None})).json()
        self.assertEqual(same["selection"], done["result"]["selection"])
        self.assertFalse(same["writer_explanation_stale"])
        self.assertTrue(changed["writer_explanation_stale"])
        self.assertNotEqual(changed["selection"]["selection_id"], same["selection"]["selection_id"])
        for body in (same, changed, reset):
            self.assertFalse(body["research_rerun"])
            self.assertTrue(body["writer_narrative_available"])
            self.assertEqual(body["decision"]["evidence"], done["result"]["decision"]["evidence"])
            self.assertEqual(body["selection"]["mapping_version"], saved["selection_context"]["metadata"]["mapping_version"])
            self.assertNotIn("selection_context", body)
        self.assertEqual(self.service.saved[key], saved)

    async def test_reset_to_original_task_default_restores_selection_and_narrative_match(self):
        done = await self.analysis()
        key = done["analysis_id"]
        await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": key, "user_alpha": .7})
        reset = (await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": key, "user_alpha": None})).json()
        self.assertEqual(reset["selection"], done["result"]["selection"])
        self.assertFalse(reset["writer_explanation_stale"])
        potential = reset["selection"]["potential_alternatives"]
        selected = writer_payload(done["result"]["decision"], done["result"]["selection"])["candidate_ids"]
        alternatives = [row for kind in potential["buckets"].values() for bucket in kind.values() for row in bucket["entries"]]
        self.assertTrue(alternatives)
        self.assertTrue(all(row["S"] is None and row["model_id"] not in selected for row in alternatives))

    async def test_old_or_corrupt_session_returns_original_raw_ranking_with_unavailable_selector(self):
        done = await self.analysis()
        key = done["analysis_id"]
        self.service.saved[key].pop("selection_context")
        body = (await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": key, "user_alpha": .5})).json()
        self.assertEqual(body["selector"]["status"], "unavailable")
        self.assertEqual(body["selector"]["error"]["code"], "selector_context_incompatible")
        self.assertTrue(body["writer_explanation_stale"])
        self.assertEqual(body["decision"], json.loads(json.dumps(decide(self.service.saved[key]["prepared"], task_type="specialized_domain", user_alpha=.5))))

    async def test_zero_candidates_strict_writer_and_trace_compatibility(self):
        done = await self.analysis(context_window=100000, hard_constraints=["context_window"])
        result = done["result"]
        self.assertEqual(result["selection"]["coverage"]["available_slots"], 0)
        self.assertEqual(result["status"], "not_supported")
        self.assertEqual(result["writer_status"], "accepted")
        self.assertFalse(result["writer_fallback"])
        self.assertIn("tool_calls", result)
        self.assertTrue(all(c["candidate_status"] == "unverified" for c in result["decision"]["candidates"].values()))

    async def test_project1_chat_renders_selection_and_run_keeps_full_result(self):
        chat = (await self.client.post("/chat", json={"message": USER_INPUT})).json()
        self.assertEqual(set(chat), {"response", "session_id", "tool_calls"})
        self.assertIn("Canonical selection", chat["response"])
        self.assertTrue(chat["tool_calls"])
        response = await self.client.get("/run", params={"question": USER_INPUT})
        events = [json.loads(s[6:]) for s in response.text.splitlines() if s.startswith("data: ")]
        self.assertEqual(events[-1]["type"], "done")
        self.assertIn("selection", events[-1]["result"])
        self.assertIn("markdown", events[-1]["result"])
