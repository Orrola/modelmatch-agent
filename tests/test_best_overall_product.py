"""Family-free product contracts over synthetic evidence; no provider calls."""

import ast
import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path

from modelmatch_schemas import WriterOutput
from recommendation import render_recommendation, validate_writer, writer_payload
from tests.test_selection_integration import synthetic_inputs
from tools.decision import _rank, decide
from tools.recommendation_selector import select_recommendations
from tools.selection_pipeline import selection_for_decision

ROOT = Path(__file__).resolve().parents[1]


class BestOverallProductTests(unittest.TestCase):
    def test_removed_modules_have_no_production_imports_or_runtime_files(self):
        removed = {"family_mapping", "family_mapping_reviewed", "family_mapping_revalidated"}
        for name in removed:
            self.assertFalse((ROOT / "tools" / f"{name}.py").exists())
        for path in [*ROOT.glob("*.py"), *(ROOT / "tools").glob("*.py")]:
            for node in ast.walk(ast.parse(path.read_text())):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                self.assertFalse(any(name.split(".")[-1] in removed for name in names), path.name)

    def test_fresh_snapshot_identity_needs_no_historical_catalog(self):
        decision, _, _, snapshot, prepared = synthetic_inputs()
        fields, context = selection_for_decision(decision, prepared, snapshot=snapshot)
        self.assertEqual(fields["selector"]["status"], "available")
        self.assertNotIn("family_mapping", context)
        self.assertNotIn("mapping_version", fields["selection"])
        self.assertEqual(set(fields["model_identity"]["models"]), set(decision["candidates"]))
        self.assertEqual(fields["selection"]["slots"]["best_overall"]["candidate"]["model_id"], "a")

    def test_highest_supported_score_wins_across_evidence_status_cohorts(self):
        decision, metadata, coverage, *_ = synthetic_inputs()
        decision["candidates"]["a"]["candidate_status"] = "provisional"
        coverage["models"]["a"]["candidate_status"] = "provisional"
        for status in ("fully_evaluable", "provisional"):
            decision["rankings"][status] = _rank(decision["candidates"], status)
        before = deepcopy(decision)
        selected = select_recommendations(decision, metadata, coverage)
        candidate = selected["slots"]["best_overall"]["candidate"]
        self.assertEqual((candidate["model_id"], candidate["candidate_status"], candidate["S"]), ("a", "provisional", 90))
        self.assertEqual(decision, before)

    def test_writer_rejects_even_resigned_secondary_candidate(self):
        decision, metadata, coverage, *_ = synthetic_inputs()
        selection = select_recommendations(decision, metadata, coverage)
        selection["slots"]["different_family"] = deepcopy(selection["slots"]["best_overall"])
        signed = {key: value for key, value in selection.items() if key != "selection_id"}
        selection["selection_id"] = hashlib.sha256(json.dumps(signed, sort_keys=True, allow_nan=False).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "retired"):
            writer_payload(decision, selection)

    def test_report_and_browser_sources_have_no_grouping_warnings(self):
        decision, metadata, coverage, *_ = synthetic_inputs()
        selection = select_recommendations(decision, metadata, coverage)
        payload = writer_payload(decision, selection)
        intent = WriterOutput(candidate_ids=payload["candidate_ids"], evidence_ids=payload["evidence_ids"], validation_steps=["task_pilot"])
        validate_writer(intent, payload)
        report = render_recommendation(decision, intent, selection)
        self.assertNotIn("family", report.lower())
        for name in ("modelmatch.html", "modelmatch.js", "recommendation_views.js"):
            source = (ROOT / "static" / name).read_text()
            self.assertNotIn("family", source.lower())

    def test_alpha_recalculation_preserves_complete_decision_and_raw_entries(self):
        decision, _, _, snapshot, prepared = synthetic_inputs()
        before = deepcopy(prepared)
        original, context = selection_for_decision(decision, prepared, snapshot=snapshot)
        for alpha in (0.3, 0.5, 0.7):
            recalculated = decide(prepared, user_alpha=alpha)
            raw = deepcopy(recalculated)
            fields, _ = selection_for_decision(recalculated, prepared, frozen_context=context)
            self.assertEqual(fields["selector"]["status"], "available")
            self.assertEqual(recalculated, raw)
            self.assertEqual(prepared, before)
            self.assertEqual(set(recalculated["candidates"]), set(decision["candidates"]))
            expected = min((c for c in recalculated["candidates"].values() if c["eligibility"] == "eligible" and c["S"] is not None), key=lambda c: (-c["S"], c["model_id"]))
            self.assertEqual(fields["selection"]["slots"]["best_overall"]["candidate"]["model_id"], expected["model_id"])
        self.assertIsNotNone(original["selection"])
