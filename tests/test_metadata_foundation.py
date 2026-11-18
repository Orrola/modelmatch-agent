"""Synthetic metadata/coverage contracts; no fixtures are real model evaluations."""

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path

from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide
from tools.evidence_coverage import analyze_evidence_coverage
from tools.family_mapping import LEGACY_MAPPING_VERSION, load_family_mapping
from tools.model_evidence import OperationalRequirement, RelevanceDecision, build_candidates
from tools.model_metadata import build_identity_sidecar

FIXTURE = Path(__file__).parent / "fixtures/phase2a_synthetic.json"


def synthetic_mapping(snapshot):
    row = snapshot["pages"][0]["data"][0]
    identity = {"name": row["name"], "slug": row.get("slug"), "release_date": row.get("release_date"),
                "creator_id": row["model_creator"]["id"], "creator_name": row["model_creator"].get("name")}
    return {"version": "synthetic-curation-v1", "families": {"synthetic:family-v1": {
        "label": "Synthetic family", "creator_id": identity["creator_id"],
        "grouping_confidence": "curated_aa_label", "provider_equivalence_status": "unknown"}},
        "records": [{"model_id": row["id"], "family_id": "synthetic:family-v1", "expected_identity": identity,
            "configuration": {"label": "Synthetic configuration", "verification_status": "aa_label_only"},
            "supporting_evidence": {"snapshot_id": snapshot["snapshot_id"], "data_mode": snapshot["data_mode"],
                "retrieved_at": snapshot["retrieved_at"], "source_url": snapshot["source_url"],
                "source_model_id": row["id"], "source_fields": deepcopy(identity),
                "basis": "Synthetic manually curated label assertion for offline testing only."}}]}


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(FIXTURE)
        self.mapping = synthetic_mapping(self.snapshot)

    def test_exact_id_join_preserves_all_rows_and_identity_fields_without_provider_guessing(self):
        original = deepcopy(self.snapshot)
        result = build_identity_sidecar(self.snapshot, mapping=self.mapping)
        rows = self.snapshot["pages"][0]["data"]
        self.assertEqual(set(result["models"]), {r["id"] for r in rows})
        self.assertEqual(result["mapping_version"], self.mapping["version"])
        for row in rows:
            meta = result["models"][row["id"]]
            self.assertEqual(meta["original_name"], row["name"])
            self.assertEqual(meta["creator_id"], row["model_creator"]["id"])
            self.assertIsNone(meta["provider"])
            self.assertEqual(meta["identity_status"], "synthetic_fixture")
        self.assertEqual(self.snapshot, original)
        self.snapshot["pages"][0]["data"].reverse()
        self.assertEqual(build_identity_sidecar(self.snapshot, mapping=self.mapping)["models"], result["models"])

    def test_seed_mapping_is_versioned_and_supports_only_label_level_claims(self):
        mapping = load_family_mapping(version=LEGACY_MAPPING_VERSION)
        self.assertEqual(mapping["version"], LEGACY_MAPPING_VERSION)
        self.assertEqual(len(mapping["records"]), 5)
        self.assertEqual(len({r["model_id"] for r in mapping["records"]}), 5)
        for record in mapping["records"]:
            self.assertEqual(record["supporting_evidence"]["source_model_id"], record["model_id"])
            self.assertEqual(record["supporting_evidence"]["snapshot_id"], "eec442cab98cf613")
            self.assertEqual(record["supporting_evidence"]["source_fields"], record["expected_identity"])
        self.assertEqual(next(iter(mapping["families"].values()))["provider_equivalence_status"], "unknown")
        mapping["records"].clear()
        self.assertEqual(len(load_family_mapping(version=LEGACY_MAPPING_VERSION)["records"]), 5)

    def test_curated_family_and_configuration_are_separate_from_official_verification(self):
        result = build_identity_sidecar(self.snapshot, mapping=self.mapping)
        first = result["models"][self.mapping["records"][0]["model_id"]]
        self.assertEqual(first["family_status"], "curated_aa_label")
        self.assertEqual(first["family_id"], "synthetic:family-v1")
        self.assertEqual(first["family"]["provider_equivalence_status"], "unknown")
        self.assertEqual(first["configuration"]["verification_status"], "aa_label_only")
        self.assertEqual(first["supporting_evidence"]["snapshot_id"], self.snapshot["snapshot_id"])

    def test_same_name_stem_never_automatically_merges_unknown_families(self):
        rows = self.snapshot["pages"][0]["data"]
        rows[1]["name"], rows[2]["name"] = "Synthetic Family (High)", "Synthetic Family (Low)"
        rows[2]["model_creator"] = deepcopy(rows[1]["model_creator"])
        result = build_identity_sidecar(self.snapshot)
        for row in rows[1:3]:
            self.assertIsNone(result["models"][row["id"]]["family_id"])
            self.assertIsNone(result["models"][row["id"]]["configuration"])
            self.assertEqual(result["models"][row["id"]]["family_status"], "unknown_unmapped")

    def test_stale_identity_or_snapshot_never_reuses_curated_evidence(self):
        model_id = self.mapping["records"][0]["model_id"]
        self.snapshot["pages"][0]["data"][0]["name"] += " New Version"
        result = build_identity_sidecar(self.snapshot, mapping=self.mapping)
        self.assertEqual(result["models"][model_id]["family_status"], "unknown_identity_mismatch")
        self.snapshot["snapshot_id"] = "synthetic-new-snapshot"
        result = build_identity_sidecar(self.snapshot, mapping=self.mapping)
        self.assertEqual(result["models"][model_id]["family_status"], "unknown_mapping_snapshot_mismatch")
        self.assertIsNone(result["models"][model_id]["supporting_evidence"])

    def test_conflicting_mapping_cross_creator_merge_and_missing_support_fail(self):
        for mode in ("duplicate", "creator", "source", "version"):
            mapping = deepcopy(self.mapping)
            if mode == "duplicate":
                mapping["records"].append(deepcopy(mapping["records"][0]))
            elif mode == "creator":
                mapping["families"]["synthetic:family-v1"]["creator_id"] = "other-creator"
            elif mode == "source":
                mapping["records"][0]["supporting_evidence"]["source_fields"]["name"] = "Other model"
            else:
                mapping["version"] = ""
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                build_identity_sidecar(self.snapshot, mapping=mapping)

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
        self.assertEqual(entry["verification"]["family"], "unknown_unmapped")
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
