"""Independent snapshot manifests and frozen-session isolation without local caches."""

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide
from tools.family_mapping import (MAPPING_VERSION, REVALIDATED_MAPPING_VERSION,
                                  REVALIDATED_SNAPSHOT_ID, load_family_mapping)
from tools.model_evidence import RelevanceDecision, build_candidates
from tools.model_metadata import build_identity_sidecar
from tools.selection_pipeline import selection_for_decision

FIXTURES = Path(__file__).parent / "fixtures"


class MappingRevalidationTests(unittest.TestCase):
    def setUp(self):
        self.old = load_family_mapping(version=MAPPING_VERSION)
        self.new = load_family_mapping(version=REVALIDATED_MAPPING_VERSION)
        self.excerpt = json.loads((FIXTURES / "aa_revalidated_identity_excerpt.json").read_text())

    def mock_inputs(self):
        snapshot = load_mock_snapshot(FIXTURES / "phase2a_synthetic.json")
        snapshot["pages"][0]["data"] = deepcopy(self.excerpt["reviewed_models"])
        mapping = deepcopy(self.new)
        # Explicit synthetic envelope tests joins only, never real benchmark evaluation.
        for record in mapping["records"]:
            record["supporting_evidence"].update({k: snapshot[k] for k in (
                "snapshot_id", "data_mode", "source_url", "retrieved_at")})
        return snapshot, mapping

    def test_revalidated_manifest_has_exact_source_identities_and_unchanged_boundaries(self):
        self.assertEqual(self.new["version"], REVALIDATED_MAPPING_VERSION)
        self.assertEqual(self.new["snapshot_id"], self.excerpt["snapshot_id"])
        self.assertEqual(self.new["snapshot_fingerprint"], self.excerpt["snapshot_fingerprint"])
        old = {r["model_id"]: r for r in self.old["records"]}
        rows = {r["id"]: r for r in self.excerpt["reviewed_models"]}
        self.assertEqual(len(self.new["records"]), 23)
        self.assertEqual(len(self.new["families"]), 10)
        for record in self.new["records"]:
            mid = record["model_id"]
            raw = rows[mid]
            identity = {k: raw[k] for k in ("name", "slug", "release_date")}
            identity.update(creator_id=raw["model_creator"]["id"], creator_name=raw["model_creator"]["name"])
            self.assertEqual(record["expected_identity"], identity)
            for key in ("family_id", "configuration", "configuration_key", "release_version", "creator_id"):
                self.assertEqual(record[key], old[mid][key])
            self.assertEqual(record["snapshot_id"], REVALIDATED_SNAPSHOT_ID)
            self.assertEqual(record["mapping_version"], REVALIDATED_MAPPING_VERSION)
            for key in ("snapshot_id", "source_url", "retrieved_at", "data_mode"):
                self.assertEqual(record["supporting_evidence"][key], self.excerpt[key])
        self.assertEqual(self.new["families"], self.old["families"])

    def test_historical_v2_is_unchanged_and_explicit_versions_remain_available(self):
        digest = hashlib.sha256(json.dumps(self.old, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, "c9314fe23f8fbfe65b0aa5fe4b943a26fff59141a732b4062fc4e4a55559b1b7")
        self.assertEqual(load_family_mapping(snapshot_id="eec442cab98cf613"), self.old)
        self.assertEqual(load_family_mapping(snapshot_id=REVALIDATED_SNAPSHOT_ID), self.new)
        self.new["records"].clear()
        self.assertEqual(len(load_family_mapping(version=REVALIDATED_MAPPING_VERSION)["records"]), 23)

    def test_new_manifest_and_identity_excerpt_never_contain_metric_evidence(self):
        excluded = {"evaluations", "pricing", "performance", "performance_v3", "G", "U", "O", "S"}
        def check(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & excluded)
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(self.new)
        check(self.excerpt)

    def test_exact_identity_drift_and_new_ids_remain_unknown(self):
        for field in ("name", "slug", "release_date", "creator_id", "creator_name"):
            snapshot, mapping = self.mock_inputs()
            row = snapshot["pages"][0]["data"][0]
            mid = row["id"]
            if field.startswith("creator_"):
                row["model_creator"][field.removeprefix("creator_")] = "synthetic-drift"
            else:
                row[field] = "synthetic-drift"
            model = build_identity_sidecar(snapshot, mapping=mapping)["models"][mid]
            self.assertEqual(model["family_status"], "unknown_identity_mismatch")
            self.assertIsNone(model["family_id"])
        snapshot, mapping = self.mock_inputs()
        row = deepcopy(snapshot["pages"][0]["data"][0])
        row["id"] = "synthetic-identical-label-new-id"
        snapshot["pages"][0]["data"].append(row)
        self.assertEqual(build_identity_sidecar(snapshot, mapping=mapping)["models"][row["id"]]["family_status"], "unknown_unmapped")

    def test_wrong_snapshot_or_retrieval_cannot_reuse_manifest(self):
        for field in ("snapshot_id", "retrieved_at", "source_url"):
            snapshot, mapping = self.mock_inputs()
            snapshot[field] = "synthetic-other-source"
            sidecar = build_identity_sidecar(snapshot, mapping=mapping)
            self.assertEqual(sidecar["coverage"]["curated_family_entries"], 0)
            self.assertTrue(all(m["family_status"] == "unknown_mapping_snapshot_mismatch" for m in sidecar["models"].values()))

    def test_recalculation_keeps_frozen_manifest_and_original_decision(self):
        snapshot, mapping = self.mock_inputs()
        prepared = build_candidates(snapshot, RelevanceDecision("Synthetic task", "finance", "strong", "Fixture only."))
        decision = decide(prepared)
        before = deepcopy(decision)
        with patch("tools.selection_pipeline.load_family_mapping", return_value=mapping) as loader:
            original, context = selection_for_decision(decision, prepared, snapshot=snapshot)
        loader.assert_called_once_with(snapshot_id=snapshot["snapshot_id"])
        self.assertEqual(original["selector"]["metadata_coverage"]["curated_family_entries"], 23)
        with patch("tools.selection_pipeline.load_family_mapping", side_effect=AssertionError("Frozen sessions must not reload")):
            adjusted = decide(prepared, user_alpha=0.7)
            repeated, frozen = selection_for_decision(adjusted, prepared, frozen_context=context)
        self.assertIs(frozen, context)
        self.assertIsNotNone(repeated["selection"])
        self.assertEqual(repeated["selection"]["mapping_version"], REVALIDATED_MAPPING_VERSION)
        self.assertEqual(decision, before)
        context["family_mapping"] = self.old
        failed, _ = selection_for_decision(adjusted, prepared, frozen_context=context)
        self.assertEqual(failed["selector"]["status"], "unavailable")
