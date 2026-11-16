"""Synthetic reference-contract regressions using the real SDK without a provider."""

import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

from modelmatch_schemas import Followup, OrchestrationLimits, Review
from orchestration import ModelMatchWorkflow
from tests.fake_modelmatch import ScriptedModel, USER_INPUT
from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide
from tools.model_evidence import OperationalRequirement, RelevanceDecision

FIXTURE = Path(__file__).parent / "fixtures/phase2a_synthetic.json"


class CatalogAwareModel(ScriptedModel):
    async def get_response(self, system_instructions, input, *args, **kwargs):
        payload = self.payload(input)
        if payload.get("stage") == "review":
            self.catalog = payload["evidence_review"]["followup_reference_catalog"]
            target = self.catalog["entries"][0]["model_id"]
            return self.text(Review(summary="Synthetic reference review.", stopping_reason="One authorized round.",
                followups=[Followup(role=r, task=f"Inspect existing {r} evidence", reason="Synthetic review.",
                                    model_ids=[target]) for r in ("A", "B", "C")]))
        return await super().get_response(system_instructions, input, *args, **kwargs)


class ReferenceCatalogTests(unittest.TestCase):
    def workflow(self, *, limit=2, requirements=()):
        snapshot = load_mock_snapshot(FIXTURE)
        model = ScriptedModel()
        workflow = ModelMatchWorkflow(model, model, limits=OrchestrationLimits(evidence_preview_size=limit))
        workflow.snapshot = snapshot
        workflow.relevance = RelevanceDecision(USER_INPUT, "finance", "strong", "Synthetic fixture mapping only.")
        workflow.requirements = requirements
        return workflow

    def test_catalog_is_bounded_gap_first_and_does_not_filter_or_score_candidates(self):
        workflow = self.workflow()
        prepared = workflow.prepared()
        before = decide(prepared)
        catalog = workflow.review_payload()["followup_reference_catalog"]
        self.assertEqual(catalog["snapshot_id"], prepared["snapshot_id"])
        self.assertEqual(catalog["returned_models"], 2)
        self.assertEqual(catalog["total_models"], len(prepared["candidates"]))
        self.assertTrue(catalog["truncated"])
        self.assertEqual(catalog["omitted_models"], len(prepared["candidates"]) - 2)
        self.assertFalse(catalog["is_candidate_filter"])
        self.assertIn("Omitted models remain", catalog["scope_policy"])
        for entry in catalog["entries"]:
            self.assertEqual(entry["name"], prepared["candidates"][entry["model_id"]]["name"])
            self.assertTrue(any(g["required"] for g in entry["evidence_gaps"]))
            for gap in entry["evidence_gaps"]:
                evidence = prepared["evidence"][gap["evidence_id"]]
                self.assertEqual(evidence["model_id"], entry["model_id"])
                self.assertEqual(gap["metric"], evidence["metric"])
                self.assertIn(gap["role"], entry["roles"])
        self.assertEqual(decide(prepared), before)

    def test_order_and_deduplication_are_deterministic(self):
        workflow = self.workflow(limit=12)
        prepared = deepcopy(workflow.prepared())
        expected = workflow.followup_reference_catalog(prepared)
        prepared["candidates"] = dict(reversed(list(prepared["candidates"].items())))
        prepared["missing_manifest"].reverse()
        for item in prepared["missing_manifest"]:
            item["missing_fields"] = list(reversed(item["missing_fields"])) * 2
        self.assertEqual(workflow.followup_reference_catalog(prepared), expected)
        ids = [entry["model_id"] for entry in expected["entries"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_model_gap_and_text_caps_are_explicit(self):
        workflow = self.workflow(limit=100, requirements=tuple(
            OperationalRequirement(f"synthetic_unverified_metric_{i}") for i in range(9)))
        rows = workflow.snapshot["pages"][0]["data"]
        template = deepcopy(rows[0])
        for i in range(20):
            row = deepcopy(template)
            row.update(id=f"synthetic-extra-{i:02}", name="Synthetic " + "x" * 180)
            rows.append(row)
        catalog = workflow.review_payload()["followup_reference_catalog"]
        self.assertEqual(catalog["max_models"], 12)
        self.assertGreater(len(catalog["entries"]), 0)
        self.assertLessEqual(len(catalog["entries"]), 12)
        self.assertLessEqual(catalog["entry_characters"], 12000)
        self.assertTrue(catalog["truncated"])
        self.assertTrue(any(e["name_truncated"] for e in catalog["entries"]))
        for entry in catalog["entries"]:
            self.assertLessEqual(len(entry["name"]), 160)
            self.assertEqual(len(entry["evidence_gaps"]), 6)
            self.assertTrue(entry["gaps_truncated"])
            self.assertGreater(entry["total_evidence_gaps"], 6)

    def test_oversized_exact_id_is_omitted_never_shortened_or_removed_from_candidates(self):
        workflow = self.workflow(limit=12)
        row = workflow.snapshot["pages"][0]["data"][0]
        row["id"] = "synthetic-long-" + "x" * 13000
        prepared = workflow.prepared()
        catalog = workflow.followup_reference_catalog(prepared)
        self.assertIn(row["id"], prepared["candidates"])
        self.assertNotIn(row["id"], {e["model_id"] for e in catalog["entries"]})
        self.assertGreater(catalog["size_omissions"], 0)
        self.assertTrue(catalog["truncated"])
        self.assertLessEqual(catalog["entry_characters"], catalog["max_entry_characters"])

    def test_missing_evidence_remains_unknown_and_hard_constraints_unverified(self):
        workflow = self.workflow(requirements=(OperationalRequirement("output_speed", 20, hard=True, statistic="mean"),))
        prepared = workflow.prepared()
        workflow.review_payload()
        decision = decide(prepared)
        self.assertIsNone(decision["candidates"]["synthetic-no-general"]["G"])
        self.assertIsNone(decision["candidates"]["synthetic-engineering"]["U"])
        legacy = decision["candidates"]["synthetic-legacy-only"]
        self.assertEqual(legacy["candidate_status"], "unverified")
        self.assertIsNone(legacy["S"])
        self.assertEqual(decision["candidates"]["synthetic-no-general"]["candidate_status"], "provisional")
        self.assertEqual(len(decision["candidates"]), len(prepared["candidates"]))


class ReferenceWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def workflow(self, model, snapshot=None):
        return ModelMatchWorkflow(model, model, snapshot_loader=AsyncMock(return_value=snapshot or load_mock_snapshot(FIXTURE)),
            limits=OrchestrationLimits(timeout_seconds=10))

    async def test_lead_uses_real_payload_ids_for_parallel_controller_followup(self):
        model = CatalogAwareModel()
        workflow = self.workflow(model)
        result = await workflow.run(USER_INPUT)
        self.assertNotEqual(result["status"], "error", result.get("error"))
        catalog_ids = {e["model_id"] for e in model.catalog["entries"]}
        starts = [e for e in result["trace"] if e["type"] == "researcher_start" and e["round_number"] == 1]
        self.assertEqual({s["role"] for s in starts}, {"A", "B", "C"})
        self.assertTrue(all(set(s["model_ids"]) <= catalog_ids for s in starts))
        self.assertEqual(len({s["context_id"] for s in starts}), 3)
        ends = [e for e in result["trace"] if e["type"] == "researcher_end" and e["context_id"] in {s["context_id"] for s in starts}]
        self.assertLess(max(s["monotonic"] for s in starts), min(e["monotonic"] for e in ends))
        self.assertEqual(result["reviews"][-1]["stage"], "review_final")
        self.assertEqual(result["diagnostics"]["stages"]["followup"]["status"], "accepted")
        self.assertEqual(result["researcher_runs"], 6)

    async def test_unknown_ids_are_rejected_with_safe_metadata_before_all_tools(self):
        tasks = [Followup(role=r, task="SYNTHETIC_PRIVATE_TASK", reason="Synthetic gap.",
                          model_ids=["SYNTHETIC_PRIVATE_INVALID", "SYNTHETIC_PRIVATE_INVALID"]) for r in ("A", "B")]
        before = [t.model_dump() for t in tasks]
        workflow = self.workflow(ScriptedModel(followups=tasks))
        with self.assertLogs("modelmatch.reliability", level="INFO") as logs:
            result = await workflow.run(USER_INPUT)
        self.assertEqual(result["error"], "unknown_model_id")
        failure = result["diagnostics"]["blocking_failure"]
        self.assertEqual(failure["affected_roles"], ["A", "B"])
        self.assertEqual(failure["invalid_target_count"], 1)
        self.assertEqual(failure["snapshot_id"], workflow.snapshot["snapshot_id"])
        events = [json.loads(row.message) for row in logs.records if row.message.startswith("{")]
        rejected = next(e for e in events if e["event"] == "followup_target_rejected")
        self.assertEqual(rejected["run_id"], result["run_id"])
        self.assertEqual(rejected["code"], rejected["rule"])
        self.assertNotIn("SYNTHETIC_PRIVATE", "\n".join(logs.output))
        self.assertEqual(result["researcher_runs"], 3)
        self.assertFalse(any(e["type"] == "researcher_start" and e["round_number"] == 1 for e in result["trace"]))
        self.assertEqual(result["diagnostics"]["stages"]["parse"]["status"], "accepted")
        self.assertEqual(result["diagnostics"]["stages"]["decision"]["status"], "not_reached")
        self.assertEqual([t.model_dump() for t in tasks], before)

    async def test_previous_snapshot_only_id_is_not_a_current_reference(self):
        previous = load_mock_snapshot(FIXTURE)
        old_id = previous["pages"][0]["data"][0]["id"]
        current = deepcopy(previous)
        current["snapshot_id"] = "synthetic-current-snapshot"
        current["pages"][0]["data"] = [r for r in current["pages"][0]["data"] if r["id"] != old_id]
        task = Followup(role="B", task="Inspect targeted evidence", reason="Synthetic stale target.", model_ids=[old_id])
        workflow = self.workflow(ScriptedModel(followups=[task]), current)
        result = await workflow.run(USER_INPUT)
        self.assertEqual(result["error"], "unknown_model_id")
        self.assertEqual(result["diagnostics"]["blocking_failure"]["snapshot_id"], current["snapshot_id"])
        self.assertEqual(result["researcher_runs"], 3)

    async def test_model_names_and_snapshot_ids_are_never_resolved_as_model_ids(self):
        snapshot = load_mock_snapshot(FIXTURE)
        for invalid in (snapshot["pages"][0]["data"][0]["name"], snapshot["snapshot_id"]):
            task = Followup(role="B", task="Inspect evidence", reason="Synthetic invalid reference.", model_ids=[invalid])
            result = await self.workflow(ScriptedModel(followups=[task])).run(USER_INPUT)
            self.assertEqual(result["error"], "unknown_model_id")
            self.assertEqual(result["researcher_runs"], 3)

    async def test_explicit_empty_authorization_keeps_full_catalog_semantics(self):
        task = Followup(role="B", task="Inspect the full shared catalog", reason="Explicit synthetic authorization.", model_ids=[])
        workflow = self.workflow(ScriptedModel(followups=[task]))
        result = await workflow.run(USER_INPUT)
        self.assertNotEqual(result["status"], "error", result.get("error"))
        self.assertEqual(set(result["researcher_results"]["B"]["models"]), set(workflow.prepared()["candidates"]))
        self.assertEqual(result["researcher_runs"], 4)
        followup = next(e for e in result["trace"] if e["type"] == "researcher_start" and e["round_number"] == 1)
        self.assertEqual(followup["model_ids"], [])

    async def test_valid_but_omitted_reference_is_not_removed_from_the_snapshot_scope(self):
        task = Followup(role="B", task="Inspect a known current model", reason="Explicit synthetic target.",
                        model_ids=["synthetic-finance"])
        workflow = self.workflow(ScriptedModel(followups=[task]))
        workflow.limits = OrchestrationLimits(timeout_seconds=10, evidence_preview_size=1)
        result = await workflow.run(USER_INPUT)
        self.assertNotEqual(result["status"], "error", result.get("error"))
        catalog = result["reviews"][0]["audit"]["followup_reference_catalog"]
        self.assertNotIn("synthetic-finance", {e["model_id"] for e in catalog["entries"]})
        self.assertEqual(result["researcher_runs"], 4)

    async def test_omitted_model_ids_cannot_silently_authorize_the_full_catalog(self):
        class MissingScopeModel(ScriptedModel):
            async def get_response(self, system_instructions, input, *args, **kwargs):
                if self.payload(input).get("stage") == "review":
                    return self.text({"summary": "Synthetic scope review.", "stopping_reason": "Synthetic cap.",
                        "followups": [{"role": "B", "task": "Inspect evidence", "reason": "Synthetic gap."}]})
                return await super().get_response(system_instructions, input, *args, **kwargs)
        result = await self.workflow(MissingScopeModel()).run(USER_INPUT)
        self.assertEqual(result["error"], "research_dispatch_not_authorized")
        self.assertEqual(result["diagnostics"]["blocking_failure"]["rule"], "full_catalog_scope_not_explicitly_authorized")
        self.assertEqual(result["researcher_runs"], 3)
