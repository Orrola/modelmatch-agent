"""Synthetic audit invariants; these fixtures are not real model evaluations."""

from copy import deepcopy
from pathlib import Path
import unittest

from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide
from tools.model_evidence import OperationalRequirement, RelevanceDecision, Workload, build_candidates


class RecommendationAuditTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        source = self.snapshot["pages"][0]["data"][0]
        rows = []
        for i in range(3):
            row = deepcopy(source)
            row.update(id=f"synthetic-related-{i}", name=f"Synthetic Family Variant {i}")
            row["evaluations"] = {"artificial_analysis_intelligence_index": 60 - i,
                                  "artificial_analysis_legal_index": 65 - i}
            row["pricing"] = {"price_1m_input_tokens": 8, "price_1m_output_tokens": 40}
            row["performance_v3"] = {"mean_time_to_first_token_seconds": 30 + i * 50,
                                     "mean_output_tokens_per_second": 100 - i}
            rows.append(row)
        self.snapshot["pages"] = [deepcopy(self.snapshot["pages"][0])]
        self.snapshot["pages"][0]["pagination"].update(has_more=False)
        self.snapshot["pages"][0]["data"] = rows
        self.relevance = RelevanceDecision("Synthetic legal analysis", "legal", "strong", "Synthetic test mapping only.")

    def test_identical_prices_and_workload_can_produce_identical_capped_penalties(self):
        prepared = build_candidates(self.snapshot, self.relevance,
            [OperationalRequirement("monthly_cost_usd", 300), OperationalRequirement("ttft", 2, statistic="mean")],
            workload=Workload(100000, 2000, 500), shortlist_size=1)
        result = decide(prepared, user_alpha=.7)
        self.assertEqual(len(result["rankings"]["fully_evaluable"]), 3)
        for item in result["candidates"].values():
            self.assertEqual(item["estimated_monthly_cost_usd"], 3600)
            self.assertEqual(item["operational_penalties"]["cost"]["deduction"], -8)
            self.assertEqual(item["operational_penalties"]["ttft"]["deduction"], -5)
            self.assertEqual(item["operational_penalties"]["output_speed"]["status"], "not_applicable")
            self.assertEqual(item["O"], -13)
            self.assertAlmostEqual(item["S"], .7 * item["G"] + .3 * item["U"] - 13)

    def test_selected_legal_index_does_not_require_other_domains_or_diversity(self):
        prepared = build_candidates(self.snapshot, self.relevance, shortlist_size=1)
        self.assertEqual(prepared["counts_before_shortlist"]["fully_evaluable"], 3)
        self.assertEqual(len(prepared["shortlists"]["fully_evaluable"]), 1)
        for alpha in (.3, .5, .6, .7):
            result = decide(prepared, user_alpha=alpha)
            self.assertEqual([r["model_id"] for r in result["rankings"]["fully_evaluable"]],
                             [f"synthetic-related-{i}" for i in range(3)])
            self.assertTrue(all(c["U"] == 65 - i for i, c in enumerate(result["candidates"].values())))

    def test_unknown_hard_specifications_block_scores_without_excluding_evidence(self):
        prepared = build_candidates(self.snapshot, self.relevance,
                                    [OperationalRequirement("context_window", 100000, hard=True)])
        result = decide(prepared)
        self.assertEqual(prepared["counts_before_shortlist"]["unverified"], 3)
        self.assertFalse(result["rankings"]["fully_evaluable"])
        for candidate in result["candidates"].values():
            self.assertIsNotNone(candidate["G"])
            self.assertIsNotNone(candidate["U"])
            self.assertIsNone(candidate["S"])
            self.assertIn("hard_constraints_unverified", candidate["score_blockers"])

    def test_missing_selected_index_remains_unknown_even_with_valid_other_indices(self):
        self.snapshot["pages"][0]["data"][0]["evaluations"]["artificial_analysis_legal_index"] = None
        self.snapshot["pages"][0]["data"][0]["evaluations"]["artificial_analysis_finance_and_accounting_index"] = 99
        result = decide(build_candidates(self.snapshot, self.relevance))
        missing = result["candidates"]["synthetic-related-0"]
        self.assertIsNone(missing["U"])
        self.assertIsNone(missing["S"])
        self.assertIn("missing_or_invalid_U", missing["score_blockers"])
        self.assertEqual(len(result["rankings"]["fully_evaluable"]), 2)
