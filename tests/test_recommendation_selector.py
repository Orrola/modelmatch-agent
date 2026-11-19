"""Deterministic Best Overall and evidence exploration over exact synthetic identities."""

import json
import unittest
from copy import deepcopy
from pathlib import Path

from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide
from tools.evidence_coverage import analyze_evidence_coverage
from tools.model_evidence import OperationalRequirement, RelevanceDecision, Workload, build_candidates
from tools.model_metadata import build_identity_sidecar
from tools.recommendation_selector import select_recommendations


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        # ID, original G/U, cost, creator and the literal configuration label.
        self.specs = [("a", 90, 100, "A", "fa"), ("b", 89, 90, "A", "fa"),
                      ("c", 88, 50, "B", "fb"), ("d", 87, 40, "C", "fc"),
                      ("e", 86, 30, "A", "fd"), ("z", 70, 10, "D", None)]

    def inputs(self, *, cost=True, requirements=None, relevance="strong"):
        rows = []
        for mid, score, price, creator, configuration_label in self.specs:
            identity = {"name": f"Synthetic {configuration_label or 'unknown'} ({mid})", "slug": f"synthetic-{mid}",
                        "release_date": "2026-11-16", "creator_id": creator, "creator_name": f"Synthetic creator {creator}"}
            rows.append({"id": mid, "name": identity["name"], "slug": identity["slug"],
                "release_date": identity["release_date"], "model_creator": {"id": creator, "name": identity["creator_name"]},
                "evaluations": {"artificial_analysis_intelligence_index": score, "artificial_analysis_finance_and_accounting_index": score},
                "pricing": {"price_1m_input_tokens": price / 2, "price_1m_output_tokens": price / 2},
                "performance_v3": {"mean_time_to_first_token_seconds": 1, "mean_output_tokens_per_second": 100}})
        self.snapshot["pages"][0]["data"] = rows
        metadata = build_identity_sidecar(self.snapshot)
        req = ([OperationalRequirement("monthly_cost_usd")] if cost else []) if requirements is None else requirements
        prepared = build_candidates(self.snapshot, RelevanceDecision("Synthetic task", "finance", relevance,
            "Synthetic task proxy only."), req, workload=Workload(1, 1000000, 1000000), shortlist_size=1)
        decision = decide(prepared, user_alpha=.5)
        coverage = analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)
        return decision, metadata, coverage

    def selected_id(self, result, role):
        candidate = result["slots"][role]["candidate"]
        return candidate["model_id"] if candidate else None

    def test_best_overall_preserves_scores_and_inputs_without_secondary_recommendations(self):
        args = self.inputs()
        before = deepcopy(args)
        result = select_recommendations(*args)
        self.assertEqual(self.selected_id(result, "best_overall"), "a")
        self.assertEqual(args, before)
        original = args[0]["candidates"]["a"]
        for key in ("G", "U", "O", "S", "evidence_ids", "eligibility", "candidate_status"):
            self.assertEqual(result["slots"]["best_overall"]["candidate"][key], original[key])
        self.assertEqual(result["coverage"]["total_candidate_entries"], 6)
        self.assertEqual(result["coverage"]["available_slots"], 1)
        for role in ("lower_cost_alternative", "different_family"):
            self.assertEqual(result["slots"][role], {"status": "unavailable", "reason_code": "recommendation_role_retired", "details": {}, "candidate": None})

    def test_names_creators_and_price_do_not_change_best_overall(self):
        self.specs = [("a", 90, 100, "A", "same"), ("b", 89, 0, "A", "same"), ("c", 88, 1, "B", "other")]
        for cost in (True, False):
            self.assertEqual(self.selected_id(select_recommendations(*self.inputs(cost=cost)), "best_overall"), "a")

    def test_exact_ties_keep_original_competition_rank_and_stable_id_order(self):
        self.specs = [("b", 90, 50, "B", "fb"), ("a", 90, 100, "A", "fa"), ("c", 80, 30, "C", "fc")]
        args = self.inputs()
        result = select_recommendations(*args)
        self.assertEqual(self.selected_id(result, "best_overall"), "a")
        self.assertEqual(result["slots"]["best_overall"]["candidate"]["raw_rank"], 1)
        self.assertEqual(result["slots"]["best_overall"]["candidate"]["raw_position"], 1)
        args[0]["candidates"] = dict(reversed(list(args[0]["candidates"].items())))
        self.assertEqual(select_recommendations(*args), result)
        json.dumps(result, allow_nan=False)

    def test_provisional_scores_remain_labeled_and_raw_group_is_preserved(self):
        result = select_recommendations(*self.inputs(relevance="partial"))
        self.assertEqual(result["comparison_cohort"], "provisional")
        self.assertEqual(result["slots"]["best_overall"]["candidate"]["candidate_status"], "provisional")

    def test_all_slots_unavailable_when_hard_requirements_cannot_be_verified(self):
        args = self.inputs(requirements=[OperationalRequirement("context_window", 100000, hard=True)])
        result = select_recommendations(*args)
        self.assertEqual(result["coverage"]["available_slots"], 0)
        self.assertTrue(all(s["status"] == "unavailable" for s in result["slots"].values()))
        self.assertEqual(result["coverage"]["eligibility"], {"eligible": 0, "unverified": 6, "ineligible": 0})

    def test_all_slots_unavailable_when_no_original_indices_are_available(self):
        self.specs = [("a", None, 100, "A", "fa")]
        result = select_recommendations(*self.inputs())
        self.assertEqual(result["coverage"]["numerically_scored"], 0)
        self.assertTrue(all(s["status"] == "unavailable" for s in result["slots"].values()))
        self.assertEqual(result["potential_alternatives"]["excluded_counts_partition"]["no_available_index_evidence"], 1)

    def test_exploration_is_bounded_and_ordered_by_identity_not_u_value(self):
        self.specs = [(f"p{i}", i, 10, "A", None) for i in range(7)]
        self.inputs(cost=False)
        for row in self.snapshot["pages"][0]["data"]:
            row["evaluations"]["artificial_analysis_intelligence_index"] = None
        m = build_identity_sidecar(self.snapshot)
        p = build_candidates(self.snapshot, RelevanceDecision("Synthetic task", "finance", "strong", "Synthetic proxy."))
        d = decide(p)
        c = analyze_evidence_coverage(self.snapshot, p, m, d)
        result = select_recommendations(d, m, c, potential_limit_per_bucket=2)
        bucket = result["potential_alternatives"]["buckets"]["U_only"]["eligible"]
        self.assertEqual([e["model_id"] for e in bucket["entries"]], ["p0", "p1"])
        self.assertEqual(bucket["total_before_limit"], 7)
        self.assertEqual(bucket["omitted"], 5)
        self.assertEqual(bucket["entries"][0]["available_index"]["value"], 0)
        self.assertTrue(all(e["S"] is None for e in bucket["entries"]))

    def missing_inputs(self, *, hard=None):
        args = self.inputs(cost=False)
        rows = self.snapshot["pages"][0]["data"]
        rows[0]["evaluations"].pop("artificial_analysis_intelligence_index")
        rows[1]["evaluations"].pop("artificial_analysis_finance_and_accounting_index")
        rows[2]["evaluations"] = {}
        metadata = build_identity_sidecar(self.snapshot)
        requirements = [] if hard is None else [hard]
        prepared = build_candidates(self.snapshot, RelevanceDecision("Synthetic task", "finance", "strong", "Synthetic proxy."), requirements)
        decision = decide(prepared)
        return decision, metadata, analyze_evidence_coverage(self.snapshot, prepared, metadata, decision)

    def test_potential_buckets_separate_u_only_g_only_and_exclude_both_missing(self):
        result = select_recommendations(*self.missing_inputs(), potential_limit_per_bucket=1)
        p = result["potential_alternatives"]
        self.assertEqual(p["buckets"]["U_only"]["eligible"]["entries"][0]["model_id"], "a")
        self.assertEqual(p["buckets"]["G_only"]["eligible"]["entries"][0]["model_id"], "b")
        self.assertEqual(p["excluded_counts_partition"]["no_available_index_evidence"], 1)
        for kinds in p["buckets"].values():
            for bucket in kinds.values():
                self.assertLessEqual(bucket["returned"], 1)
                self.assertTrue(all(e["S"] is None and "rank" not in e for e in bucket["entries"]))
        coverage = result["coverage"]
        self.assertEqual(coverage["missing_G"], 2)
        self.assertEqual(coverage["missing_U"], 2)
        self.assertEqual(sum(coverage["index_partition"].values()), 6)

    def test_unknown_hard_evidence_and_known_violations_are_not_conflated(self):
        unknown = select_recommendations(*self.missing_inputs(hard=OperationalRequirement("context_window", 100000, hard=True)))
        self.assertEqual(unknown["potential_alternatives"]["buckets"]["U_only"]["unverified"]["total_before_limit"], 1)
        violated = select_recommendations(*self.missing_inputs(hard=OperationalRequirement("input_price", 0, hard=True)))
        self.assertEqual(violated["potential_alternatives"]["excluded_counts_partition"]["known_hard_constraint_violation"], 6)
        self.assertTrue(all(bucket["returned"] == 0 for states in violated["potential_alternatives"]["buckets"].values() for bucket in states.values()))

    def test_snapshot_identity_and_foreign_evidence_mismatch_fail_closed(self):
        for mode in ("snapshot", "fingerprint", "identity", "evidence", "rank"):
            d, m, c = self.inputs()
            if mode == "snapshot":
                m["snapshot_id"] = "other-snapshot"
            elif mode == "fingerprint":
                c["snapshot_fingerprint"] = "other-content"
            elif mode == "identity":
                m["models"]["a"]["original_name"] = "Other exact model"
            elif mode == "evidence":
                next(iter(d["evidence"].values()))["snapshot_id"] = "old-snapshot"
            else:
                d["rankings"]["fully_evaluable"][0]["rank"] = 9
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                select_recommendations(d, m, c)

    def test_bounded_exploration_limits_are_validated(self):
        args = self.missing_inputs()
        for value in (-1, 21, True, "5"):
            with self.assertRaises(ValueError):
                select_recommendations(*args, potential_limit_per_bucket=value)
        result = select_recommendations(*args, potential_limit_per_bucket=0)
        self.assertEqual(result["potential_alternatives"]["buckets"]["U_only"]["eligible"]["omitted"], 1)


    def test_equal_numeric_values_do_not_permit_cross_model_index_evidence(self):
        self.specs[1] = ("b", 90, 90, "A", "fa")
        d, m, c = self.inputs()
        c["models"]["a"]["G"]["evidence_ids"] = c["models"]["b"]["G"]["evidence_ids"]
        with self.assertRaises(ValueError):
            select_recommendations(d, m, c)
