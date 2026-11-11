"""Phase 2A offline tests. Synthetic inputs are NEVER real benchmark evidence."""

import copy
import json
import unittest
from pathlib import Path

from tools.artificial_analysis import load_mock_snapshot
from tools.model_evidence import (
    DOMAIN_INDICES, OperationalRequirement as Op, RelevanceDecision, Workload, build_candidates,
)
from scripts.candidate_audit import audit

FIXTURE = Path(__file__).parent / "fixtures/phase2a_synthetic.json"


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(FIXTURE)

    def decision(self, domain="finance", status="strong"):
        return RelevanceDecision(f"Synthetic {domain} task", domain, status,
                                 "Test-only documented mapping; not a validated product scenario.")

    def build(self, domain="finance", requirements=(), **kwargs):
        return build_candidates(self.snapshot, self.decision(domain), requirements, **kwargs)

    def test_finance_only_requires_selected_index(self):
        result = self.build()
        counts = result["counts_before_shortlist"]
        self.assertEqual(counts["total"], 5)
        self.assertEqual((counts["A_valid"], counts["B_valid"], counts["C_valid"]), (4, 3, 5))
        self.assertEqual(counts["fully_evaluable"], 2)
        self.assertTrue(result["researcher_evidence"]["B"]["synthetic-finance"]["valid"])
        # This model has NO healthcare or other four domain indices.
        self.assertEqual(result["candidates"]["synthetic-finance"]["candidate_status"], "fully_evaluable")

    def test_engineering_and_healthcare_dynamic_pools(self):
        for domain in ("engineering", "healthcare"):
            with self.subTest(domain=domain):
                result = self.build(domain)
                self.assertEqual(result["counts_before_shortlist"]["B_valid"], 1)
                self.assertEqual(result["candidate_groups"]["fully_evaluable"], [f"synthetic-{domain}"])

    def test_unsupported_domain_has_no_fabricated_u(self):
        decision = RelevanceDecision("Creative marketing", None, "none", "No validated task-equivalent AA index.")
        result = build_candidates(self.snapshot, decision)
        self.assertEqual(result["counts_before_shortlist"]["B_valid"], 0)
        self.assertEqual(result["counts_before_shortlist"]["provisional"], 5)
        self.assertTrue(all(c["U"] is None for c in result["candidates"].values()))

    def test_missing_g_and_u_preserved_without_zero(self):
        result = self.build()
        no_g = result["candidates"]["synthetic-no-general"]
        self.assertIsNone(no_g["G"])
        self.assertEqual(no_g["eligibility"], "eligible")
        self.assertEqual(no_g["candidate_status"], "provisional")
        no_u = result["candidates"]["synthetic-engineering"]
        self.assertIsNone(no_u["U"])
        issue = next(m for m in result["missing_manifest"] if m["model_id"] == "synthetic-engineering")
        self.assertTrue(any(f["role"] == "B" and f["reason"] == "field_absent" for f in issue["missing_fields"]))

    def test_no_legacy_fallback_for_missing_operations(self):
        result = self.build(requirements=(Op("ttft", 2), Op("output_speed", 50)))
        legacy = result["candidates"]["synthetic-legacy-only"]
        self.assertFalse(legacy["evidence_completeness"]["C"])
        self.assertEqual(legacy["candidate_status"], "provisional")
        self.assertEqual(legacy["eligibility"], "eligible")
        self.assertFalse(any("median" in e["metric"] for e in result["evidence"].values()))

    def test_hard_failure_vs_unknown_and_completeness(self):
        result = self.build(requirements=(Op("ttft", 1, hard=True, statistic="mean"),))
        failed = result["candidates"]["synthetic-finance"]
        self.assertTrue(failed["evidence_completeness"]["C"])
        self.assertEqual(failed["candidate_status"], "ineligible")
        unknown = result["candidates"]["synthetic-legacy-only"]
        self.assertFalse(unknown["evidence_completeness"]["C"])
        self.assertEqual(unknown["candidate_status"], "unverified")

    def test_known_hard_fail_takes_precedence_over_unknown(self):
        result = self.build(requirements=(Op("ttft", 1, hard=True), Op("context_window", 100000, hard=True)))
        self.assertEqual(result["candidates"]["synthetic-finance"]["candidate_status"], "ineligible")

    def test_partial_relevance_is_b_valid_but_provisional(self):
        result = build_candidates(self.snapshot, self.decision(status="partial"))
        self.assertTrue(result["researcher_evidence"]["B"]["synthetic-finance"]["valid"])
        self.assertEqual(result["counts_before_shortlist"]["fully_evaluable"], 0)

    def test_monthly_cost_requires_workload_and_both_prices(self):
        req = (Op("monthly_cost_usd", 1, hard=True),)
        result = self.build(requirements=req)
        self.assertEqual(result["counts_before_shortlist"]["unverified"], 5)
        result = self.build(requirements=req, workload=Workload(1000, 1000, 1000))
        self.assertEqual(result["candidates"]["synthetic-finance"]["eligibility"], "ineligible")
        self.assertEqual(result["candidates"]["synthetic-legacy-only"]["eligibility"], "unverified")
        derived = next(e for e in result["evidence"].values() if e["model_id"] == "synthetic-finance" and e["metric"] == "monthly_cost_usd")
        self.assertEqual(derived["value"], 3)
        self.assertEqual(len(derived["input_evidence_ids"]), 2)

    def test_speed_hard_constraint_uses_lower_bound(self):
        result = self.build(requirements=(Op("output_speed", 60, hard=True),))
        self.assertEqual(result["candidates"]["synthetic-finance"]["eligibility"], "ineligible")
        self.assertEqual(result["candidates"]["synthetic-engineering"]["eligibility"], "eligible")

    def test_context_and_deployment_stay_unknown(self):
        result = self.build(requirements=(Op("context_window", 100000, hard=True), Op("deployment", "on-prem", hard=True)))
        self.assertEqual(result["counts_before_shortlist"]["unverified"], 5)
        pending = [e for e in result["evidence"].values() if e["source_type"] == "official_docs_pending"]
        self.assertTrue(all(e["value"] is None and e["source_url"] is None for e in pending))

    def test_p95_is_not_satisfied_by_mean(self):
        result = self.build(requirements=(Op("ttft", 10, hard=True, statistic="p95"),))
        self.assertEqual(result["counts_before_shortlist"]["unverified"], 5)

    def test_traceability_and_index_versions(self):
        original = copy.deepcopy(self.snapshot)
        result = self.build()
        for e in result["evidence"].values():
            self.assertEqual(e["snapshot_id"], self.snapshot["snapshot_id"])
            self.assertEqual(e["data_mode"], "mock")
            self.assertIn(e["model_id"], result["candidates"])
        g = next(e for e in result["evidence"].values() if e["model_id"] == "synthetic-finance" and e["metric"].endswith("intelligence_index"))
        u = next(e for e in result["evidence"].values() if e["model_id"] == "synthetic-finance" and e["metric"].endswith("finance_and_accounting_index"))
        self.assertEqual(g["index_version"], "synthetic-only")
        self.assertIsNone(u["index_version"])
        self.assertEqual(self.snapshot, original)

    def test_exact_id_join_independent_of_list_order(self):
        first = self.build()
        self.snapshot["pages"][0]["data"].reverse()
        second = self.build()
        self.assertEqual(first, second)

    def test_duplicate_ids_rejected(self):
        rows = self.snapshot["pages"][0]["data"]
        rows[1]["id"] = rows[0]["id"]
        with self.assertRaisesRegex(ValueError, "Duplicate AA"):
            self.build()

    def test_shortlist_counts_precede_limits_and_include_all_statuses(self):
        result = self.build(shortlist_size=1)
        self.assertEqual(result["counts_before_shortlist"]["total"], 5)
        self.assertEqual(result["counts_before_shortlist"]["fully_evaluable"], 2)
        self.assertEqual(len(result["shortlists"]["fully_evaluable"]), 1)
        self.assertEqual(len(result["candidates"]), 5)
        self.assertEqual(result["shortlists"]["fully_evaluable"], ["synthetic-legacy-only"])
        self.assertEqual(self.build(shortlist_size=0)["shortlists"]["provisional"], [])
        unlimited = self.build(shortlist_size=None)
        self.assertEqual(len(unlimited["shortlists"]["provisional"]), 3)

    def test_zero_valid_bool_nan_invalid(self):
        rows = self.snapshot["pages"][0]["data"]
        rows[0]["evaluations"]["artificial_analysis_intelligence_index"] = 0
        rows[1]["evaluations"]["artificial_analysis_intelligence_index"] = True
        rows[2]["evaluations"]["artificial_analysis_intelligence_index"] = float("nan")
        result = self.build()
        self.assertTrue(result["researcher_evidence"]["A"]["synthetic-finance"]["valid"])
        self.assertFalse(result["researcher_evidence"]["A"]["synthetic-engineering"]["valid"])
        self.assertFalse(result["researcher_evidence"]["A"]["synthetic-healthcare"]["valid"])
        json.dumps(result, allow_nan=False)

    def test_no_scoring_fields_or_penalties(self):
        result = self.build(requirements=(Op("ttft", 0.5),))
        self.assertTrue(result["candidates"]["synthetic-finance"]["evidence_completeness"]["C"])
        for candidate in result["candidates"].values():
            self.assertFalse({"score", "O", "alpha", "final_score"} & candidate.keys())

    def test_relevance_and_requirements_validation(self):
        with self.assertRaises(ValueError):
            RelevanceDecision("Finance", "finance", "strong", "")
        with self.assertRaises(ValueError):
            RelevanceDecision("Unknown", "creative", "strong", "No index")
        with self.assertRaises(ValueError):
            Op("ttft", -1)
        with self.assertRaises(ValueError):
            self.build(requirements=(Op("ttft", 1), Op("ttft", 2)))

    def test_invalid_negative_operations_preserved_as_invalid(self):
        self.snapshot["pages"][0]["data"][0]["pricing"]["price_1m_input_tokens"] = -1
        result = self.build(requirements=(Op("input_price"),))
        candidate = result["candidates"]["synthetic-finance"]
        self.assertFalse(candidate["evidence_completeness"]["C"])
        issue = next(m for m in result["missing_manifest"] if m["model_id"] == "synthetic-finance")
        self.assertTrue(any(i["reason"] == "negative_operational_value" for i in issue["missing_fields"]))

    def test_candidate_audit_reports_both_profiles_without_network(self):
        text, results = audit(self.snapshot, shortlist_size=1)
        self.assertEqual(len(results), 8)
        self.assertIn("mock", text)
        self.assertEqual(results["finance-index_only"]["counts_before_shortlist"]["fully_evaluable"], 2)
        self.assertEqual(results["finance-operations"]["counts_before_shortlist"]["fully_evaluable"], 1)
        self.assertEqual(results["unsupported-index_only"]["counts_before_shortlist"]["B_valid"], 0)

    def test_mixed_versions_rejected(self):
        page = copy.deepcopy(self.snapshot["pages"][0])
        self.snapshot["pages"][0]["pagination"]["has_more"] = True
        page["pagination"]["page"] = 2
        page["data"] = []
        page["intelligence_index_version"] = "another-synthetic-version"
        self.snapshot["pages"].append(page)
        with self.assertRaisesRegex(ValueError, "Mixed Intelligence"):
            self.build()


if __name__ == "__main__":
    unittest.main()
