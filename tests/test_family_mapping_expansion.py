"""Reviewed identities and synthetic replay invariants; no provider or local-cache dependency."""

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts.family_mapping_audit import PROFILES, REFERENCES, audit, prepare_profile
from tests import test_recommendation_selector as selector_tests
from tools.artificial_analysis import load_mock_snapshot
from tools.family_mapping import LEGACY_MAPPING_VERSION, MAPPING_VERSION, load_family_mapping
from tools.model_metadata import build_identity_sidecar
from tools.recommendation_selector import select_recommendations
from tools.selection_pipeline import selection_for_decision

FIXTURES = Path(__file__).parent / "fixtures"


class FamilyMappingExpansionTests(unittest.TestCase):
    def setUp(self):
        self.excerpt = json.loads((FIXTURES / "aa_family_identity_excerpt.json").read_text())
        self.mapping = load_family_mapping()
        self.records = {r["model_id"]: r for r in self.mapping["records"]}

    def identity_snapshot(self):
        # Identity-only real excerpts are transplanted into an explicit mock envelope.
        # No benchmark numbers are created or represented as real evaluations.
        snapshot = load_mock_snapshot(FIXTURES / "phase2a_synthetic.json")
        snapshot["pages"][0]["data"] = deepcopy(self.excerpt["reviewed_models"] + self.excerpt["unmapped_review_candidates"])
        return snapshot

    def adapted_test_mapping(self, snapshot):
        mapping = deepcopy(self.mapping)
        for record in mapping["records"]:
            record["supporting_evidence"].update({k: snapshot[k] for k in ("snapshot_id", "data_mode", "source_url", "retrieved_at")})
        return mapping

    def test_reviewed_members_match_retained_source_identity_and_versions(self):
        self.assertEqual(self.mapping["version"], MAPPING_VERSION)
        self.assertEqual(len(self.records), 23)
        self.assertEqual(len(self.mapping["families"]), 10)
        self.assertEqual(set(self.records), {r["id"] for r in self.excerpt["reviewed_models"]})
        configuration_keys = set()
        for raw in self.excerpt["reviewed_models"]:
            record = self.records[raw["id"]]
            self.assertEqual(record["expected_identity"], {"name": raw["name"], "slug": raw["slug"],
                "release_date": raw["release_date"], "creator_id": raw["model_creator"]["id"],
                "creator_name": raw["model_creator"]["name"]})
            self.assertEqual(record["snapshot_id"], self.excerpt["snapshot_id"])
            self.assertEqual(record["creator_id"], raw["model_creator"]["id"])
            self.assertEqual(record["release_version"]["release_date"], raw["release_date"])
            self.assertEqual(record["review_status"], "reviewed_aa_product_label_only")
            self.assertEqual(record["mapping_version"], MAPPING_VERSION)
            evidence = record["supporting_evidence"]
            self.assertEqual(evidence["source_fields"], record["expected_identity"])
            self.assertEqual(evidence["source_url"], self.excerpt["source_url"])
            self.assertEqual(evidence["retrieved_at"], self.excerpt["retrieved_at"])
            self.assertTrue(evidence["basis"])
            self.assertEqual(evidence["review"]["mapping_version"], MAPPING_VERSION)
            self.assertEqual(record["configuration"]["verification_status"], "aa_label_only")
            self.assertIsNone(record["configuration"]["quantization_label"])
            self.assertIsNone(record["configuration"]["preview_label"])
            configuration_keys.add(record["configuration_key"])
        self.assertEqual(len(configuration_keys), 23)

    def test_same_product_configurations_stay_distinct_without_weight_equivalence(self):
        first = self.records["909ed0ba-bcc5-4f38-8162-08a4e187a772"]
        second = self.records["0d3eaafd-54ed-4f78-bdd7-05a2db883986"]
        self.assertEqual(first["family_id"], second["family_id"])
        self.assertNotEqual(first["configuration_key"], second["configuration_key"])
        self.assertEqual(first["configuration"]["reasoning_label"], "High")
        self.assertEqual(second["configuration"]["reasoning_label"], "Medium")
        self.assertEqual(self.mapping["families"][first["family_id"]]["provider_equivalence_status"], "unknown")

    def test_same_creator_different_products_versions_and_release_boundaries_remain_separate(self):
        anth = [r for r in self.records.values() if r["expected_identity"]["creator_name"] == "Anthropic"]
        self.assertEqual(len({r["family_id"] for r in anth}), 4)
        for family_id, family in self.mapping["families"].items():
            members = [r for r in self.records.values() if r["family_id"] == family_id]
            self.assertEqual({r["creator_id"] for r in members}, {family["creator_id"]})
            self.assertEqual({r["release_version"]["release_date"] for r in members}, {family["release_date"]})
            self.assertEqual({r["release_version"]["product_version"] for r in members}, {family["product_version"]})
            self.assertEqual({r["configuration"]["routing_label"] for r in members}, {family["routing_label"]})
            self.assertEqual({r["configuration"]["size_label"] for r in members}, {family["size_label"]})

    def test_missing_mapping_does_not_merge_size_preview_or_unreviewed_configurations(self):
        snapshot = self.identity_snapshot()
        sidecar = build_identity_sidecar(snapshot, mapping=self.adapted_test_mapping(snapshot))
        self.assertEqual(sidecar["coverage"]["curated_family_entries"], 23)
        for raw in self.excerpt["unmapped_review_candidates"]:
            meta = sidecar["models"][raw["id"]]
            self.assertIsNone(meta["family_id"])
            self.assertIsNone(meta["configuration"])
            self.assertEqual(meta["family_status"], "unknown_unmapped")
        full = self.records["e994a6e0-d36b-4dab-8ae1-c1b469e4d9e2"]
        self.assertEqual(full["configuration"]["size_label"], "Full")
        self.assertIsNone(sidecar["models"]["38a98e3d-779b-49ec-b005-230a3a72088a"]["family_id"])

    def test_identity_changes_never_inherit_curated_group(self):
        for field, value in (("release_date", "2026-11-17"), ("name", "Synthetic changed Preview product"),
                             ("name", "Synthetic changed 8B size"), ("name", "Synthetic changed INT4 configuration"),
                             ("name", "Synthetic different fallback routing"), ("slug", "synthetic-new-version")):
            snapshot = self.identity_snapshot()
            mapping = self.adapted_test_mapping(snapshot)
            row = snapshot["pages"][0]["data"][0]
            mid = row["id"]
            row[field] = value
            meta = build_identity_sidecar(snapshot, mapping=mapping)["models"][mid]
            self.assertIsNone(meta["family_id"])
            self.assertEqual(meta["family_status"], "unknown_identity_mismatch")

    def test_new_id_with_identical_label_is_unknown_not_automatically_grouped(self):
        snapshot = self.identity_snapshot()
        mapping = self.adapted_test_mapping(snapshot)
        row = deepcopy(snapshot["pages"][0]["data"][0])
        row["id"] = "synthetic-new-id-same-label"
        snapshot["pages"][0]["data"].append(row)
        meta = build_identity_sidecar(snapshot, mapping=mapping)["models"][row["id"]]
        self.assertIsNone(meta["family_id"])

    def test_review_manifest_rejects_cross_creator_and_release_assignments(self):
        from tools.family_mapping_reviewed import REVIEWED_GROUPS
        for field, value in (("creator_id", "synthetic-other-creator"), ("release_date", "2026-11-17")):
            groups = deepcopy(REVIEWED_GROUPS)
            groups[0]["members"][0]["identity"][field] = value
            with patch("tools.family_mapping_reviewed.REVIEWED_GROUPS", groups):
                with self.assertRaises(ValueError):
                    load_family_mapping()

    def test_historical_support_never_transfers_to_a_different_snapshot_or_retrieval(self):
        snapshot = self.identity_snapshot()
        original = build_identity_sidecar(snapshot, mapping=self.mapping)
        self.assertEqual(original["coverage"]["curated_family_entries"], 0)
        for field, value in (("snapshot_id", "synthetic-new-snapshot"), ("retrieved_at", "2026-11-17T00:00:00Z")):
            source = deepcopy(snapshot)
            mapping = self.adapted_test_mapping(source)
            source[field] = value
            changed = build_identity_sidecar(source, mapping=mapping)
            self.assertEqual(changed["coverage"]["curated_family_entries"], 0)
            for mid in self.records:
                self.assertEqual(changed["models"][mid]["family_status"], "unknown_mapping_snapshot_mismatch")

    def test_legacy_mapping_is_byte_semantically_unchanged_and_returns_isolated_copies(self):
        legacy = load_family_mapping(version=LEGACY_MAPPING_VERSION)
        digest = hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, "76c459a774b9e1e27aeb88d9bd6b1665f68c0d563eeb4c44c4f089c4c6dd8eca")
        self.assertEqual(len(legacy["records"]), 5)
        legacy["records"].clear()
        self.mapping["records"].clear()
        self.assertEqual(len(load_family_mapping(version=LEGACY_MAPPING_VERSION)["records"]), 5)
        self.assertEqual(len(load_family_mapping()["records"]), 23)
        with self.assertRaises(ValueError):
            load_family_mapping(version="unreviewed-future-version")


class MappingReplayTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(FIXTURES / "phase2a_synthetic.json")

    def test_five_primary_profiles_do_not_invent_task_mappings_or_workload(self):
        profiles = {p["key"]: p for p in PROFILES}
        self.assertEqual(set(profiles), {"coding", "financial", "ecommerce", "customer_support", "legal"})
        for name in ("coding", "customer_support", "ecommerce"):
            prepared = prepare_profile(self.snapshot, profiles[name])
            self.assertEqual(prepared["relevance"]["match_status"], "none")
            self.assertTrue(all(c["U"] is None for c in prepared["candidates"].values()))
        prepared = prepare_profile(self.snapshot, profiles["ecommerce"])
        for candidate in prepared["researcher_evidence"]["C"].values():
            self.assertEqual(candidate["workload"], {"monthly_requests": 100000, "avg_input_tokens": 2000, "avg_output_tokens": 500})
        finance = prepare_profile(self.snapshot, profiles["financial"])
        self.assertTrue(all(all(v is None for v in c["workload"].values()) for c in finance["researcher_evidence"]["C"].values()))
        legal = prepare_profile(self.snapshot, profiles["legal"])
        self.assertTrue(all(c["eligibility"] == "unverified" for c in legal["candidates"].values()))
        self.assertTrue(all(p["fidelity"] == "domain_reference_not_task_replay" for p in REFERENCES[:2]))

    def test_replay_is_deterministic_preserves_source_and_separates_reference_frequency(self):
        original = deepcopy(self.snapshot)
        before = load_family_mapping(version=LEGACY_MAPPING_VERSION)
        after = load_family_mapping()
        report = audit(self.snapshot, before, after)
        self.assertEqual(report, audit(self.snapshot, before, after))
        self.assertEqual(self.snapshot, original)
        self.assertEqual(report["data_mode"], "mock")
        for section in report["scenarios"].values():
            for scenario in section.values():
                self.assertTrue(scenario["raw_decision_unchanged"])
        for name in ("coding", "customer_support", "ecommerce", "legal"):
            self.assertEqual(report["scenarios"]["primary"][name]["scored_candidates"], 0)
        self.assertTrue(all(p["primary_top20_appearances"] <= 1 for p in report["priority_candidates"]))
        self.assertEqual(sum(p["primary_top20_appearances"] for p in report["priority_candidates"]),
                         len(report["scenarios"]["primary"]["financial"]["raw_top20"]))

    def test_mapping_updates_change_selection_not_scores_eligibility_or_missing_policy(self):
        case = selector_tests.SelectorTests()
        case.setUp()
        decision, after, coverage = case.inputs()
        before = build_identity_sidecar(case.snapshot, mapping={"version": "synthetic-before", "records": [], "families": {}})
        before_coverage = deepcopy(coverage)
        before_coverage["mapping_version"] = before["mapping_version"]
        for mid in before_coverage["models"]:
            before_coverage["models"][mid]["verification"]["family"] = before["models"][mid]["family_status"]
        original = deepcopy(decision)
        initial = select_recommendations(decision, before, before_coverage)
        updated = select_recommendations(decision, after, coverage)
        self.assertEqual(initial["coverage"]["available_slots"], 1)
        self.assertEqual(updated["coverage"]["available_slots"], 3)
        self.assertEqual(initial["slots"]["best_overall"]["candidate"]["model_id"], updated["slots"]["best_overall"]["candidate"]["model_id"])
        self.assertEqual(updated, select_recommendations(decision, after, coverage))
        self.assertEqual(decision, original)
        self.assertEqual(initial["potential_alternatives"], updated["potential_alternatives"])

    def test_frozen_v1_session_does_not_reload_v2_during_recalculation(self):
        profile = next(p for p in PROFILES if p["key"] == "financial")
        prepared = prepare_profile(self.snapshot, profile)
        from tools.decision import decide
        decision = decide(prepared, task_type="specialized_domain")
        with patch("tools.selection_pipeline.load_family_mapping", return_value=load_family_mapping(version=LEGACY_MAPPING_VERSION)):
            original, context = selection_for_decision(decision, prepared, snapshot=self.snapshot)
        with patch("tools.selection_pipeline.load_family_mapping", side_effect=AssertionError("Frozen mapping must not reload")):
            repeated, _ = selection_for_decision(decision, prepared, frozen_context=context)
        self.assertEqual(original, repeated)
        self.assertEqual(repeated["selection"]["mapping_version"], LEGACY_MAPPING_VERSION)
