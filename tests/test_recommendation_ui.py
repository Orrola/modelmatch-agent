"""Synthetic recommendation presentation and read-only identity projection contracts."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import httpx

from tests.test_selection_integration import synthetic_inputs
from tools.decision import decide
from tools.evidence_coverage import analyze_evidence_coverage
from tools.model_evidence import OperationalRequirement, RelevanceDecision, Workload, build_candidates
from tools.model_metadata import build_identity_sidecar
from tools.recommendation_selector import select_recommendations
from tools.selection_pipeline import identity_presentation

ROOT = Path(__file__).resolve().parents[1]
JSC = shutil.which("jsc") or "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"


def presentation_fixtures():
    """Use existing fictional test models; never load or refresh actual benchmark data."""
    result = {}
    for key, options in (("three", {}), ("two", {"cost": False}),
        ("policy", {"requirements": [OperationalRequirement("input_price", 100)]}),
        ("partial", {"match_status": "partial"}),
        ("penalties", {"requirements": [OperationalRequirement("monthly_cost_usd", 20), OperationalRequirement("ttft", .5, statistic="mean")]}),
        ("one", {"specs": [("a", 90, 100, "A", None)]}),
        ("zero", {"requirements": [OperationalRequirement("context_window", 100000, hard=True)]}),
        ("states", {"requirements": [OperationalRequirement("input_price", 30, hard=True)]})):
        _, _, _, snapshot, _, mapping = synthetic_inputs(**{k: v for k, v in options.items() if k not in ("user_alpha", "match_status")})
        if key in ("three", "zero", "states"):
            template = deepcopy(snapshot["pages"][0]["data"][-1])
            for i in range(12):
                row = deepcopy(template)
                row.update(id=f"synthetic-limited-{i}", name=f"Synthetic limited evidence {i}", slug=f"synthetic-limited-{i}")
                row["evaluations"]["artificial_analysis_intelligence_index"] = None if i % 2 else 30
                row["evaluations"]["artificial_analysis_finance_and_accounting_index"] = 40 if i % 2 else None
                if key == "states" and i % 2:
                    row["pricing"]["price_1m_input_tokens"] = None
                snapshot["pages"][0]["data"].append(row)
        if key == "three":
            row = next(row for row in snapshot["pages"][0]["data"] if row["id"] == "d")
            row["evaluations"]["artificial_analysis_intelligence_index"] = 97
            row["evaluations"]["artificial_analysis_finance_and_accounting_index"] = 78
        metadata = build_identity_sidecar(snapshot, mapping=mapping)
        requirements = options.get("requirements", [OperationalRequirement("monthly_cost_usd")] if options.get("cost", True) else [])
        prepared = build_candidates(snapshot, RelevanceDecision("Synthetic UI test", "finance", options.get("match_status", "strong"), "Synthetic fixture proxy only."),
            requirements, workload=Workload(1, 1000000, 1000000), shortlist_size=6)
        decision = decide(prepared, user_alpha=options.get("user_alpha", .5))
        coverage = analyze_evidence_coverage(snapshot, prepared, metadata, decision)
        selection = select_recommendations(decision, metadata, coverage)
        result[key] = {"decision": decision, "selection": selection, "model_identity": identity_presentation(metadata),
            "selector": {"status": "limited_metadata"}, "writer_status": "accepted", "writer_fallback": False,
            "status": ("provisional" if selection["comparison_cohort"] == "provisional" else "supported") if selection["coverage"]["available_slots"] else "not_supported", "trace": [], "tool_calls": [],
            "markdown": "Synthetic original report. Not real AA evaluations."}
        if key == "three":
            frozen_three = (snapshot, metadata, prepared)
    snapshot, metadata, prepared = frozen_three
    for key, alpha in (("adjusted", .7), ("reset", None)):
        decision = decide(prepared, user_alpha=alpha)
        coverage = analyze_evidence_coverage(snapshot, prepared, metadata, decision)
        result[key] = {**result["three"], "decision": decision,
            "selection": select_recommendations(decision, metadata, coverage)}
    result["failure"] = {**deepcopy(result["three"]), "selection": None, "model_identity": None,
        "selector": {"status": "unavailable"}, "writer_status": "skipped", "report_fallback": True}
    result["legacy"] = {key: value for key, value in result["three"].items() if key not in ("selection", "model_identity", "selector")}
    result["mismatch"] = deepcopy(result["three"])
    for meta in result["mismatch"]["model_identity"]["models"].values():
        meta["family_status"] = "unknown_mapping_snapshot_mismatch"
        meta["family_id"] = None
    result["mismatch"]["model_identity"]["families"] = {}
    return result


class IdentityPresentationTests(unittest.TestCase):
    def test_projection_preserves_binding_and_exact_backend_membership_without_raw_snapshot(self):
        _, metadata, _, *_ = synthetic_inputs()
        before = deepcopy(metadata)
        projection = identity_presentation(metadata)
        self.assertEqual(set(projection["models"]), set(metadata["models"]))
        self.assertEqual(projection["mapping_version"], metadata["mapping_version"])
        self.assertEqual(projection["snapshot_fingerprint"], metadata["snapshot_fingerprint"])
        self.assertEqual(projection["families"]["fa"]["model_ids"], ["a", "b"])
        self.assertIsNone(projection["models"]["z"]["family_id"])
        self.assertIsNone(projection["models"]["a"]["provider"])
        self.assertNotIn("pages", projection)
        self.assertNotIn("evidence", projection)
        projection["models"]["a"]["configuration"].clear()
        self.assertEqual(metadata, before)

    def test_all_fixture_recommendations_and_alternatives_keep_real_contracts(self):
        fixtures = presentation_fixtures()
        for key, count in (("one", 1), ("two", 2), ("three", 3), ("zero", 0)):
            self.assertEqual(fixtures[key]["selection"]["coverage"]["available_slots"], count)
        for fixture in fixtures.values():
            selection = fixture.get("selection")
            if not selection:
                continue
            for group in selection["potential_alternatives"]["buckets"].values():
                for bucket in group.values():
                    self.assertTrue(all(row["S"] is None for row in bucket["entries"]))
                    self.assertTrue(all(row["eligibility"] != "ineligible" for row in bucket["entries"]))


class RecommendationViewTests(unittest.TestCase):
    @unittest.skipUnless(Path(JSC).is_file(), "JavaScriptCore is unavailable.")
    def test_best_overall_coverage_alternatives_raw_rankings_identity_and_stale_narrative(self):
        fixture = presentation_fixtures()
        source = "const fixtures=" + json.dumps(fixture) + ";\n" + (ROOT / "tests/recommendation_views_contract.js").read_text()
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "recommendation-ui-test.js"
            script.write_text(source)
            result = subprocess.run([JSC, str(script)], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Recommendation view checks passed", result.stdout)


class RecommendationUiHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_asset_and_identity_fields_survive_sse_chat_and_recalculation(self):
        import app
        service = app.app.state.modelmatch
        service.saved.clear(); service.recent.clear(); service.active = 0
        from tools.chat_sessions import ChatSessionStore
        service.chat_sessions = ChatSessionStore()
        with patch.dict(os.environ, {"MODELMATCH_OFFLINE": "1", "MODELMATCH_CHAT_EVALUATION_ENABLED": "1"}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url="http://offline-test") as client:
                asset = await client.get("/recommendation-views.js")
                self.assertEqual(asset.status_code, 200)
                self.assertEqual(asset.headers["cache-control"], "no-cache")
                response = await client.post("/api/modelmatch/analyze", json={"question": "Analyze financial documents for a finance team."})
                events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                done = events[-1]
                identity = done["result"]["model_identity"]
                self.assertEqual(set(identity["models"]), set(done["result"]["decision"]["candidates"]))
                current = (await client.post("/api/modelmatch/recalculate", json={"analysis_id": done["analysis_id"], "user_alpha": .7})).json()
                self.assertEqual(current["model_identity"], identity)
                self.assertTrue(current["writer_explanation_stale"])
                self.assertFalse(current["research_rerun"])
                chat = (await client.post("/chat", json={"message": "Analyze financial documents for a finance team."})).json()
                self.assertEqual(set(chat), {"response", "session_id", "tool_calls"})
                self.assertIn("Canonical selection", chat["response"])
                self.assertTrue(chat["tool_calls"])
                compatibility = await client.get("/run", params={"question": "Analyze financial documents for a finance team."})
                frames = [json.loads(line[6:]) for line in compatibility.text.splitlines() if line.startswith("data: ")]
                self.assertEqual(frames[-1]["type"], "done")
                self.assertIn("model_identity", frames[-1]["result"])
                self.assertIn("markdown", frames[-1])
