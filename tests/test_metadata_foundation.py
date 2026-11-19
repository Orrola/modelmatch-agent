"""Synthetic metadata/coverage contracts; no fixtures are real model evaluations."""

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path

from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide
from tools.evidence_coverage import analyze_evidence_coverage
from tools.model_evidence import OperationalRequirement, RelevanceDecision, build_candidates
from tools.model_metadata import build_identity_sidecar

FIXTURE = Path(__file__).parent / "fixtures/phase2a_synthetic.json"


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(FIXTURE)

    def test_exact_id_join_preserves_all_source_fields_without_guessing(self):
        original = deepcopy(self.snapshot)
        result = build_identity_sidecar(self.snapshot)
        for row in self.snapshot["pages"][0]["data"]:
            meta = result["models"][row["id"]]
            self.assertEqual(meta["original_name"], row["name"])
            self.assertEqual(meta["original_slug"], row.get("slug"))
            self.assertEqual(meta["release_date"], row.get("release_date"))
            self.assertEqual(meta["creator_id"], row["model_creator"]["id"])
            self.assertIsNone(meta["provider"])
        self.assertEqual(self.snapshot, original)
        self.snapshot["pages"][0]["data"].reverse()
        self.assertEqual(build_identity_sidecar(self.snapshot)["models"], result["models"])

    def test_similar_names_never_merge_exact_ids(self):
        rows = self.snapshot["pages"][0]["data"]
        rows[1]["name"] = rows[2]["name"] = "Synthetic model configuration"
        result = build_identity_sidecar(self.snapshot)
        self.assertEqual(len(result["models"]), len(rows))
        self.assertNotEqual(result["models"][rows[1]["id"]]["model_id"], result["models"][rows[2]["id"]]["model_id"])
        self.assertNotIn("families", result)
        self.assertNotIn("mapping_version", result)

    def test_duplicate_snapshot_ids_fail_closed(self):
        rows = self.snapshot["pages"][0]["data"]
        rows.append(deepcopy(rows[0]))
        with self.assertRaises(ValueError):
            build_identity_sidecar(self.snapshot)

    def test_live_snapshot_digest_is_checked_without_reading_any_api(self):
        self.snapshot.update(data_mode="live", source_url="https://example.test/aa", retrieved_at="2026-11-16T00:00:00Z")
        self.snapshot["snapshot_id"] = hashlib.sha256(json.dumps(self.snapshot["pages"], sort_keys=True).encode()).hexdigest()[:16]
        self.assertEqual(len(build_identity_sidecar(self.snapshot)["models"]), 5)
        self.snapshot["pages"][0]["data"][0]["name"] += " Changed"
        with self.assertRaises(ValueError):
            build_identity_sidecar(self.snapshot)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(FIXTURE)
        self.relevance = RelevanceDecision("Synthetic finance analysis", "finance", "strong", "Synthetic test proxy only.")

    def inputs(self, requirements=()):
        prepared = build_candidates(self.snapshot, self.relevance, requirements, shortlist_size=1)
        metadata = build_identity_sidecar(self.snapshot)
        return prepared, metadata, decide(prepared)

    def test_g_only_u_only_and_both_missing_remain_unranked_with_no_fabricated_scores(self):
        rows = self.snapshot["pages"][0]["data"]
        rows[-1]["evaluations"] = {}
        prepared, metadata, decision = self.inputs()
        before = deepcopy((self.snapshot, prepared, metadata, decision))
        result = analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)
        cases = {"synthetic-engineering": (True, False), "synthetic-no-general": (False, True),
                 "synthetic-legacy-only": (False, False)}
        for model_id, flags in cases.items():
            entry = result["models"][model_id]
            self.assertEqual((entry["G"]["available"], entry["U"]["available"]), flags)
            self.assertIsNone(entry["decision_S"])
            self.assertFalse(entry["scoring_completeness"]["evidence_complete"])
            alt = next(e for e in result["potential_alternatives"]["by_eligibility"]["eligible"] if e["model_id"] == model_id)
            self.assertIsNone(alt["S"])
            self.assertNotIn("rank", alt)
            self.assertTrue(alt["missing_evidence_reasons"])
        self.assertEqual((self.snapshot, prepared, metadata, decision), before)
        self.assertEqual(result["counts"]["total"], 5)

    def test_known_violation_keeps_complete_evidence_and_ineligibility_separate(self):
        prepared, metadata, decision = self.inputs([OperationalRequirement("input_price", 0, hard=True)])
        result = analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)
        entry = result["models"]["synthetic-finance"]
        self.assertTrue(entry["scoring_completeness"]["evidence_complete"])
        self.assertEqual(entry["eligibility"], "ineligible")
        self.assertFalse(entry["decision_score_available"])
        self.assertFalse(any(e["model_id"] == "synthetic-finance" for pool in result["potential_alternatives"]["by_eligibility"].values() for e in pool))

    def test_unknown_hard_specification_is_unverified_not_an_eligible_alternative(self):
        prepared, metadata, decision = self.inputs([OperationalRequirement("context_window", 100000, hard=True)])
        result = analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)
        entry = result["models"]["synthetic-finance"]
        self.assertTrue(entry["G"]["available"] and entry["U"]["available"])
        self.assertFalse(entry["scoring_completeness"]["operational_evidence_complete"])
        self.assertEqual(entry["eligibility"], "unverified")
        self.assertEqual(entry["verification"]["official_specifications"], "unknown")
        self.assertEqual(len(result["potential_alternatives"]["by_eligibility"]["eligible"]), 0)
        self.assertTrue(all(e["S"] is None for e in result["potential_alternatives"]["by_eligibility"]["unverified"]))

    def test_valid_raw_indices_keep_existing_score_without_promoting_verification(self):
        prepared, metadata, decision = self.inputs()
        result = analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)
        entry = result["models"]["synthetic-finance"]
        self.assertEqual(entry["decision_S"], decision["candidates"]["synthetic-finance"]["S"])
        self.assertEqual(entry["verification"]["benchmark_evidence"], "synthetic_fixture")
        self.assertEqual(entry["verification"]["official_specifications"], "not_requested")

    def test_unsupported_domain_never_substitutes_another_u(self):
        self.relevance = RelevanceDecision("Synthetic unsupported task", None, "none", "No relevant index.")
        prepared, metadata, decision = self.inputs()
        result = analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)
        self.assertEqual(result["counts"]["U_available"], 0)
        self.assertEqual(result["counts"]["decision_score_available"], 0)
        self.assertTrue(all(e["U"]["value"] is None for e in result["models"].values()))

    def test_same_id_with_different_content_and_foreign_snapshot_evidence_are_rejected(self):
        for mode in ("metadata", "prepared", "decision", "evidence", "content", "identity", "source_value", "subset"):
            prepared, metadata, decision = self.inputs()
            snapshot = deepcopy(self.snapshot)
            if mode == "metadata":
                metadata["snapshot_id"] = "other-snapshot"
            elif mode in ("prepared", "decision"):
                (prepared if mode == "prepared" else decision)["snapshot_id"] = "other-snapshot"
            elif mode == "evidence":
                next(iter(prepared["evidence"].values()))["snapshot_id"] = "other-snapshot"
            elif mode == "content":
                snapshot["pages"][0]["data"][0]["name"] = "Other identity"
            elif mode == "identity":
                metadata["models"]["synthetic-finance"]["creator_id"] = "other-creator"
            elif mode == "source_value":
                evidence_id = next(iter(prepared["evidence"]))
                prepared["evidence"][evidence_id]["value"] = "forged"
                decision["evidence"][evidence_id]["value"] = "forged"
            else:
                decision["candidates"].pop("synthetic-finance")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                analyze_evidence_coverage(snapshot, prepared, metadata, decision)

    def test_fabricated_score_for_missing_index_is_rejected(self):
        prepared, metadata, decision = self.inputs()
        decision["candidates"]["synthetic-no-general"].update(S=99, score_status="computed")
        with self.assertRaises(ValueError):
            analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)

    def test_output_is_deterministic_and_json_serializable(self):
        prepared, metadata, decision = self.inputs()
        first = analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)
        prepared["candidates"] = dict(reversed(list(prepared["candidates"].items())))
        decision["candidates"] = dict(reversed(list(decision["candidates"].items())))
        second = analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)
        self.assertEqual(first, second)
        json.dumps(first, allow_nan=False)
