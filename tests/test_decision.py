"""Offline deterministic tests using fictional inputs, not model evaluations."""

import copy
import json
import unittest
from pathlib import Path

from tools.artificial_analysis import load_mock_snapshot
from tools.decision import (
    TASK_DEFAULTS, WeightPolicy, capped_linear_penalty, decide, evaluate_operations, resolve_weights, weight_controls,
)
from tools.model_evidence import OperationalRequirement as Op, RelevanceDecision, Workload, build_candidates

FIXTURE = Path(__file__).parent / "fixtures/phase2a_synthetic.json"


class WeightTests(unittest.TestCase):
    def test_all_task_defaults(self):
        expected = {"general_assistant": 0.7, "tool_agent": 0.5, "reasoning_analysis": 0.5,
                    "coding_assistant": 0.4, "specialized_domain": 0.3, "mixed_or_unknown": 0.6}
        self.assertEqual(TASK_DEFAULTS, expected)
        for task, alpha in expected.items():
            with self.subTest(task=task):
                weights = resolve_weights(task)
                self.assertEqual(weights["alpha"], alpha)
                self.assertEqual(weights["weight_mode"], "task_default")
                self.assertEqual(weights["source"], f"task_defaults.{task}")
                self.assertTrue(weights["default_policy_is_provisional"])

    def test_fallback_is_point_six(self):
        for task in (None, "unrecognized", ""):
            weights = resolve_weights(task)
            self.assertEqual(weights["alpha"], 0.6)
            self.assertEqual(weights["weight_mode"], "fallback_default")
            self.assertEqual(weights["task_type"], task)

    def test_override_wins_including_zero_and_one(self):
        for alpha in (0, 0.33, 1):
            weights = resolve_weights("general_assistant", alpha)
            self.assertEqual(weights["alpha"], alpha)
            self.assertEqual(weights["weight_mode"], "user_override")
            self.assertEqual(weights["suggested_alpha"], 0.7)
            self.assertAlmostEqual(weights["use_case_weight"], 1 - alpha)

    def test_invalid_weights_are_rejected_not_clamped(self):
        for value in (-0.1, 1.1, True, "0.6", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_weights(user_alpha=value)

    def test_configurable_policy_is_isolated(self):
        custom = {**TASK_DEFAULTS, "tool_agent": 0.45}
        policy = WeightPolicy(custom, fallback_alpha=0.55)
        custom["tool_agent"] = 0.9
        self.assertEqual(resolve_weights("tool_agent", policy=policy)["alpha"], 0.45)
        self.assertEqual(resolve_weights("other", policy=policy)["alpha"], 0.55)
        self.assertEqual(resolve_weights("tool_agent")["alpha"], 0.5)
        with self.assertRaises(ValueError):
            WeightPolicy({"tool_agent": 2})

    def test_frontend_reset_clears_override_and_restores_suggestion(self):
        weights = resolve_weights("coding_assistant", 0.8)
        controls = weight_controls(weights)
        self.assertEqual(controls["detected_task_type"], "coding_assistant")
        self.assertEqual(controls["slider"]["value"], 0.8)
        reset = controls["reset_to_default"]
        self.assertIsNone(reset["user_alpha"])
        restored = resolve_weights(reset["task_type"], reset["user_alpha"])
        self.assertEqual(restored["alpha"], 0.4)
        self.assertEqual(restored["weight_mode"], "task_default")
        json.dumps(controls, allow_nan=False)


class PenaltyTests(unittest.TestCase):
    def test_capped_linear_excess(self):
        for actual, target, cap, expected in ((100, 100, 8, 0), (50, 100, 8, 0),
                                              (125, 100, 8, -2), (150, 100, 8, -4),
                                              (200, 100, 8, -8), (1000, 100, 8, -8),
                                              (1.5, 1, 5, -2.5)):
            self.assertAlmostEqual(capped_linear_penalty(actual, target, cap), expected)

    def test_speed_shortfall(self):
        for actual, expected in ((200, 0), (100, 0), (75, -0.5), (50, -1), (0, -2)):
            self.assertEqual(capped_linear_penalty(actual, 100, 2, minimum=True), expected)

    def test_zero_targets_are_explicit(self):
        self.assertEqual(capped_linear_penalty(0, 0, 8), 0)
        self.assertEqual(capped_linear_penalty(1, 0, 8), -8)
        self.assertEqual(capped_linear_penalty(1, 0, 5), -5)
        self.assertEqual(capped_linear_penalty(0, 0, 2, minimum=True), 0)

    def test_invalid_penalty_inputs_are_not_missing_as_zero(self):
        for actual in (None, True, -1, float("nan"), float("inf")):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                capped_linear_penalty(actual, 1, 8)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(FIXTURE)
        self.relevance = RelevanceDecision("Synthetic finance task", "finance", "strong",
                                            "Synthetic relevance assertion for deterministic tests only.")

    def prepare(self, requirements=(), **kwargs):
        return build_candidates(self.snapshot, self.relevance, requirements, **kwargs)

    def model(self, result, mid="synthetic-finance"):
        return result["candidates"][mid]

    def test_raw_indices_no_normalization(self):
        result = decide(self.prepare())
        c = self.model(result)
        self.assertEqual((c["G"], c["U"], c["O"], c["S"]), (20, 30, 0, 24))
        self.assertEqual(c["weights"]["alpha"], 0.6)
        self.assertEqual(c["weights"]["weight_mode"], "fallback_default")

    def test_all_three_penalties_and_cost_provenance(self):
        prepared = self.prepare((Op("monthly_cost_usd", 2), Op("ttft", 1), Op("output_speed", 100)),
                                workload=Workload(1000, 1000, 1000))
        c = self.model(decide(prepared))
        self.assertEqual(c["estimated_monthly_cost_usd"], 3)
        self.assertEqual(c["O"], -10)
        self.assertEqual(c["S"], 14)
        breakdown = c["operational_penalties"]
        self.assertEqual([breakdown[k]["deduction"] for k in ("cost", "ttft", "output_speed")], [-4, -5, -1])
        self.assertEqual(len(breakdown["cost"]["evidence_ids"]), 3)

    def test_total_penalty_floor_and_no_bonus(self):
        self.snapshot["pages"][0]["data"][0]["performance_v3"]["mean_output_tokens_per_second"] = 0
        prepared = self.prepare((Op("monthly_cost_usd", 1), Op("ttft", 1), Op("output_speed", 100)),
                                workload=Workload(1000, 1000, 1000))
        c = self.model(decide(prepared))
        self.assertEqual(c["O"], -15)
        prepared = self.prepare((Op("ttft", 100), Op("output_speed", 0)))
        self.assertEqual(self.model(decide(prepared))["O"], 0)

    def test_no_inferred_constraints_or_penalties(self):
        c = self.model(decide(self.prepare()))
        self.assertEqual(c["O"], 0)
        self.assertTrue(all(p["status"] == "not_applicable" for p in c["operational_penalties"].values()))

    def test_researcher_c_operations_match_final_decision_without_ranking(self):
        prepared = self.prepare((Op("ttft", 1),))
        operations = evaluate_operations(prepared)
        final = decide(prepared)
        for model_id, c in operations.items():
            self.assertNotIn("S", c)
            self.assertNotIn("G", c)
            self.assertNotIn("U", c)
            self.assertEqual(c["O"], final["candidates"][model_id]["O"])
            self.assertEqual(c["operational_penalties"], final["candidates"][model_id]["operational_penalties"])

    def test_missing_g_even_with_zero_general_weight(self):
        c = self.model(decide(self.prepare(), user_alpha=0), "synthetic-no-general")
        self.assertIsNone(c["G"])
        self.assertIsNone(c["S"])
        self.assertIn("missing_or_invalid_G", c["score_blockers"])

    def test_missing_u_even_with_zero_use_case_weight(self):
        c = self.model(decide(self.prepare(), user_alpha=1), "synthetic-engineering")
        self.assertIsNone(c["U"])
        self.assertIsNone(c["S"])
        self.assertEqual(c["candidate_status"], "provisional")

    def test_missing_soft_operations_are_unknown_not_free(self):
        c = self.model(decide(self.prepare((Op("ttft", 1),))), "synthetic-legacy-only")
        self.assertIsNone(c["O"])
        self.assertIsNone(c["S"])
        self.assertIsNone(c["operational_penalties"]["ttft"]["deduction"])
        self.assertEqual(c["operational_penalties"]["ttft"]["status"], "unknown")

    def test_missing_workload_prevents_cost_and_score(self):
        c = self.model(decide(self.prepare((Op("monthly_cost_usd", 10),))))
        self.assertIsNone(c["estimated_monthly_cost_usd"])
        self.assertIsNone(c["O"])
        self.assertIsNone(c["S"])
        self.assertEqual(c["operational_penalties"]["cost"]["status"], "unknown")

    def test_unknown_measurement_remains_unknown_at_zero_target(self):
        c = self.model(decide(self.prepare((Op("ttft", 0),))), "synthetic-legacy-only")
        self.assertIsNone(c["S"])
        self.assertIsNone(c["operational_penalties"]["ttft"]["deduction"])

    def test_zero_workload_is_valid_and_cost_is_zero(self):
        c = self.model(decide(self.prepare((Op("monthly_cost_usd", 0),), workload=Workload(0, 100, 100))))
        self.assertEqual(c["estimated_monthly_cost_usd"], 0)
        self.assertEqual(c["operational_penalties"]["cost"]["deduction"], 0)
        self.assertIsNotNone(c["S"])

    def test_measurement_only_request_creates_no_soft_target(self):
        c = self.model(decide(self.prepare((Op("ttft"),))))
        self.assertEqual(c["operational_penalties"]["ttft"]["status"], "not_applicable")
        self.assertEqual(c["O"], 0)

    def test_other_requested_unknown_soft_evidence_blocks_scoring(self):
        c = self.model(decide(self.prepare((Op("deployment", "on-prem"),))))
        self.assertIsNone(c["S"])
        self.assertIsNone(c["O"])
        self.assertEqual(c["candidate_status"], "provisional")

    def test_undefined_soft_penalty_policy_is_not_silently_ignored(self):
        c = self.model(decide(self.prepare((Op("input_price", 0.5),))))
        self.assertIsNone(c["S"])
        self.assertIn("no_soft_penalty_policy_for_input_price", c["score_blockers"])

    def test_missing_price_prevents_cost_even_with_complete_workload(self):
        prepared = self.prepare((Op("monthly_cost_usd", 10),), workload=Workload(1, 1, 1))
        c = self.model(decide(prepared), "synthetic-legacy-only")
        self.assertIsNone(c["estimated_monthly_cost_usd"])
        self.assertIsNone(c["S"])

    def test_hard_budget_fails_without_penalty_compensation(self):
        prepared = self.prepare((Op("monthly_cost_usd", 1, hard=True),), workload=Workload(1000, 1000, 1000))
        c = self.model(decide(prepared))
        self.assertEqual(c["eligibility"], "ineligible")
        self.assertIsNone(c["S"])
        self.assertEqual(c["operational_penalties"]["cost"]["status"], "not_applicable")

    def test_unknown_hard_constraints_excluded_from_rankings(self):
        result = decide(self.prepare((Op("context_window", 100000, hard=True),)))
        self.assertEqual(result["rankings"]["fully_evaluable"], [])
        self.assertEqual(result["rankings"]["provisional"], [])
        self.assertTrue(all(c["candidate_status"] == "unverified" and c["S"] is None for c in result["candidates"].values()))

    def test_hard_latency_and_speed(self):
        for requirement in (Op("ttft", 1, hard=True), Op("output_speed", 60, hard=True)):
            c = self.model(decide(self.prepare((requirement,))))
            self.assertEqual(c["candidate_status"], "ineligible")
            self.assertIsNone(c["S"])

    def test_p95_is_incompatible(self):
        for hard in (False, True):
            c = self.model(decide(self.prepare((Op("ttft", 10, hard=hard, statistic="p95"),))))
            self.assertIsNone(c["S"])
            self.assertEqual(c["candidate_status"], "unverified" if hard else "provisional")

    def test_legacy_metric_tampering_is_not_accepted_as_v3(self):
        prepared = self.prepare((Op("ttft", 1),))
        check = prepared["researcher_evidence"]["C"]["synthetic-finance"]["checks"][0]
        record = prepared["evidence"][check["evidence_id"]]
        record["metric"] = "performance.median_time_to_first_token_seconds"
        record["statistic"] = "median"
        c = self.model(decide(prepared))
        self.assertIsNone(c["S"])
        self.assertEqual(c["operational_penalties"]["ttft"]["status"], "unknown")

    def test_partial_relevance_has_separate_provisional_ranking(self):
        self.relevance = RelevanceDecision("Synthetic task", "finance", "partial", "Proxy with untested coverage.")
        result = decide(self.prepare())
        self.assertEqual(result["rankings"]["fully_evaluable"], [])
        self.assertTrue(result["rankings"]["provisional"])
        self.assertEqual(self.model(result)["candidate_status"], "provisional")

    def test_unsupported_domain_never_scores(self):
        self.relevance = RelevanceDecision("Creative task", None, "none", "No supported index.")
        result = decide(self.prepare())
        self.assertTrue(all(c["S"] is None for c in result["candidates"].values()))

    def two_model_pool(self):
        rows = self.snapshot["pages"][0]["data"][:2]
        rows[0]["evaluations"]["artificial_analysis_intelligence_index"] = 80
        rows[0]["evaluations"]["artificial_analysis_finance_and_accounting_index"] = 20
        rows[1]["evaluations"]["artificial_analysis_intelligence_index"] = 40
        rows[1]["evaluations"]["artificial_analysis_finance_and_accounting_index"] = 90
        self.snapshot["pages"][0]["data"] = rows

    def test_ranking_changes_with_weights_and_ignores_display_shortlist(self):
        self.two_model_pool()
        prepared = self.prepare(shortlist_size=0)
        result = decide(prepared, user_alpha=0.6)
        self.assertEqual(result["rankings"]["fully_evaluable"][0]["model_id"], "synthetic-engineering")
        result = decide(prepared, user_alpha=0.7)
        self.assertEqual(result["rankings"]["fully_evaluable"][0]["model_id"], "synthetic-finance")
        self.assertEqual(len(result["rankings"]["fully_evaluable"]), 2)

    def test_sensitivity_includes_actual_alpha_and_rank_changes(self):
        self.two_model_pool()
        result = decide(self.prepare(), user_alpha=0.65)
        self.assertEqual([s["alpha"] for s in result["sensitivity"]], [0.5, 0.6, 0.65, 0.7])
        actual = next(s for s in result["sensitivity"] if s["is_actual_alpha"])
        self.assertEqual(actual["rankings"], result["rankings"])
        self.assertTrue(all(r["rank_delta"] == 0 for r in actual["rank_changes"]["fully_evaluable"]))
        other = next(s for s in result["sensitivity"] if s["alpha"] == 0.5)
        self.assertTrue(any(r["rank_delta"] != 0 for r in other["rank_changes"]["fully_evaluable"]))

    def test_sensitivity_deduplicates_actual_alpha(self):
        result = decide(self.prepare(), user_alpha=0.6)
        self.assertEqual(len(result["sensitivity"]), 3)

    def test_sensitivity_keeps_operational_evidence_and_penalties_fixed(self):
        result = decide(self.prepare((Op("ttft", 1),)), user_alpha=0.33)
        c = self.model(result)
        self.assertEqual(c["O"], -5)
        for scenario in result["sensitivity"]:
            ranking = scenario["rankings"]["fully_evaluable"]
            scored = next(row for row in ranking if row["model_id"] == "synthetic-finance")
            alpha = scenario["alpha"]
            self.assertAlmostEqual(scored["S"], alpha * 20 + (1 - alpha) * 30 - 5)

    def test_ties_share_rank_with_deterministic_id_order(self):
        self.two_model_pool()
        rows = self.snapshot["pages"][0]["data"]
        rows[1]["evaluations"] = copy.deepcopy(rows[0]["evaluations"])
        result = decide(self.prepare())
        ranking = result["rankings"]["fully_evaluable"]
        self.assertEqual([r["rank"] for r in ranking], [1, 1])
        self.assertEqual([r["model_id"] for r in ranking], sorted(r["model_id"] for r in ranking))

    def test_evidence_ids_snapshot_and_weight_metadata(self):
        result = decide(self.prepare(), task_type="specialized_domain")
        c = self.model(result)
        self.assertEqual(c["snapshot_id"], self.snapshot["snapshot_id"])
        self.assertEqual(c["weights"]["alpha"], 0.3)
        self.assertEqual(c["weights"]["task_type"], "specialized_domain")
        self.assertTrue(all(eid in result["evidence"] for eid in c["evidence_ids"]))
        self.assertTrue(c["assumptions"])

    def test_cross_model_and_snapshot_joins_rejected(self):
        for field, value in (("model_id", "wrong-model"), ("snapshot_id", "wrong-snapshot")):
            prepared = self.prepare()
            eid = prepared["candidates"]["synthetic-finance"]["evidence_ids"][0]
            prepared["evidence"][eid][field] = value
            with self.assertRaises(ValueError):
                decide(prepared)

    def test_no_input_mutation_and_json_serializable(self):
        prepared = self.prepare((Op("ttft", 1),))
        original = copy.deepcopy(prepared)
        first = decide(prepared)
        self.assertEqual(prepared, original)
        self.assertEqual(first, decide(prepared))
        json.dumps(first, allow_nan=False)

    def test_negative_utility_is_not_clamped_or_normalized(self):
        self.snapshot["pages"][0]["data"][0]["evaluations"]["artificial_analysis_intelligence_index"] = -10
        self.snapshot["pages"][0]["data"][0]["evaluations"]["artificial_analysis_finance_and_accounting_index"] = -20
        self.assertLess(self.model(decide(self.prepare()))["S"], 0)


if __name__ == "__main__":
    unittest.main()
