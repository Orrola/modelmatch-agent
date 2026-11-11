"""Provider-free HTTP/SDK regressions for the dedicated web and provisional chat APIs."""

import asyncio
import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
import app as web
from modelmatch_web import WebInput, AnalysisService
from tools.decision import decide


TASK = "Analyze financial documents for a finance team."


class WebApplicationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MODELMATCH_OFFLINE": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.service = web.app.state.modelmatch
        self.service.saved.clear()
        self.service.recent.clear()
        self.service.active = 0
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://offline-test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def analyze(self, **values):
        response = await self.client.post("/api/modelmatch/analyze", json={"question": TASK, **values})
        self.assertEqual(response.status_code, 200, response.text[:1000])
        self.events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(self.events[0]["type"], "start")
        self.assertEqual(self.events[-1]["type"], "done", self.events[-1])
        return self.events[-1]

    async def test_pages_health_and_configuration_are_local(self):
        for path in ("/", "/modelmatch", "/modelmatch.js", "/modelmatch.css", "/healthz", "/api/modelmatch/config"):
            self.assertEqual((await self.client.get(path)).status_code, 200)
        config = (await self.client.get("/api/modelmatch/config")).json()
        self.assertEqual(config["mode"], "offline_synthetic")
        self.assertFalse(config["contract_verified"])
        self.assertFalse(config["grounding_enabled"])
        self.assertFalse((await self.client.get("/healthz")).json()["provider_checked"])

    async def test_sse_contract_has_interpretation_stages_and_synthetic_decision(self):
        done = await self.analyze()
        result = done["result"]
        self.assertEqual(result["execution_mode"], "offline_synthetic")
        self.assertEqual(result["integration_usage"]["model_requests"], 0)
        self.assertEqual(result["decision"]["data_mode"], "mock")
        self.assertTrue(any(e["type"] == "interpretation" for e in self.events))
        self.assertTrue(any(e["type"] == "stage" and e["stage"] == "review" for e in self.events))
        self.assertFalse(result["writer_fallback"])
        self.assertEqual(self.service.active, 0)

    async def test_optional_fields_do_not_block_quality_analysis(self):
        result = (await self.analyze())["result"]
        self.assertIn("decision", result)
        self.assertEqual(result["plan"]["constraints"], [])
        self.assertTrue(all(v is None for v in result["plan"]["workload"].values()))

    async def test_explicit_monthly_cost_without_workload_requests_clarification(self):
        result = (await self.analyze(monthly_budget=100))["result"]
        self.assertEqual(result["status"], "clarification_needed")
        self.assertIn("Monthly cost", result["questions"][0])
        self.assertEqual(result["tool_calls"], [])

    async def test_unclear_task_requests_clarification_without_tools(self):
        result = (await self.analyze(question="help"))["result"]
        self.assertEqual(result["status"], "clarification_needed")
        self.assertEqual(result["researcher_runs"], 0)

    async def test_structured_input_binds_quotes_and_mean_measurements(self):
        result = (await self.analyze(monthly_budget=100, monthly_requests=1000,
            avg_input_tokens=2000, avg_output_tokens=500, ttft=2, output_speed=40, user_alpha=.7))["result"]
        self.assertIn("decision", result)
        constraints = {c["metric"]: c for c in result["plan"]["constraints"]}
        self.assertEqual(constraints["ttft"]["statistic"], "mean")
        self.assertEqual(constraints["output_speed"]["target"], 40)
        self.assertEqual(result["decision"]["weights"]["alpha"], .7)
        self.assertEqual(result["decision"]["weights"]["weight_mode"], "user_override")

    async def test_small_numeric_form_values_retain_valid_provenance_quotes(self):
        result = (await self.analyze(ttft=0.0000001, user_alpha=0.0000001))["result"]
        self.assertIn("decision", result)
        self.assertEqual(result["decision"]["weights"]["alpha"], 0.0000001)

    async def test_unknown_context_evidence_remains_unverified(self):
        decision = (await self.analyze(context_window=100000, hard_constraints=["context_window"]))["result"]["decision"]
        self.assertTrue(all(c["candidate_status"] == "unverified" for c in decision["candidates"].values()))
        self.assertTrue(any(e["evidence_status"] == "unknown" for e in decision["evidence"].values()))

    async def test_known_budget_violations_and_unknown_prices_stay_separate(self):
        decision = (await self.analyze(monthly_budget=0, monthly_requests=1, avg_input_tokens=1,
            avg_output_tokens=1, hard_constraints=["monthly_budget"]))["result"]["decision"]
        statuses = {c["candidate_status"] for c in decision["candidates"].values()}
        self.assertIn("ineligible", statuses)
        self.assertIn("unverified", statuses)

    async def test_missing_indices_never_become_zero_scores(self):
        decision = (await self.analyze())["result"]["decision"]
        missing = [c for c in decision["candidates"].values() if c["G"] is None or c["U"] is None]
        self.assertTrue(missing)
        self.assertTrue(all(c["S"] is None for c in missing))
        self.assertEqual(decision["counts_before_shortlist"]["total"], 5)

    async def test_unsupported_domain_has_no_invented_use_case_index(self):
        result = (await self.analyze(question="Write original poetry for an arts club."))["result"]
        self.assertEqual(result["decision"]["relevance"]["match_status"], "none")
        self.assertTrue(all(c["U"] is None and c["S"] is None for c in result["decision"]["candidates"].values()))

    async def test_weight_override_and_reset_reuse_evidence_and_preserve_writer(self):
        done = await self.analyze(user_alpha=.8)
        key = done["analysis_id"]
        original = deepcopy(self.service.saved[key]["result"])
        with patch.object(self.service, "run", new_callable=AsyncMock) as run:
            for alpha in (.7, None):
                response = await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": key, "user_alpha": alpha})
                self.assertEqual(response.status_code, 200)
                body = response.json()
                expected = decide(self.service.saved[key]["prepared"], task_type="mixed_or_unknown", user_alpha=alpha)
                self.assertEqual(body["decision"], json.loads(json.dumps(expected)))
                self.assertFalse(body["research_rerun"])
                self.assertTrue(body["writer_explanation_stale"])
                self.assertEqual(body["writer_alpha"], .8)
            run.assert_not_awaited()
        self.assertEqual(self.service.saved[key]["result"], original)

    async def test_recalculation_reports_matching_original_writer_weights(self):
        done = await self.analyze()
        result = (await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": done["analysis_id"], "user_alpha": .6})).json()
        self.assertFalse(result["writer_explanation_stale"])

    async def test_expired_and_evidenceless_analysis_ids_have_explicit_errors(self):
        done = await self.analyze(question="help")
        response = await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": done["analysis_id"], "user_alpha": .5})
        self.assertEqual(response.status_code, 409)
        self.service.saved[done["analysis_id"]]["expires"] = 0
        response = await self.client.post("/api/modelmatch/recalculate", json={"analysis_id": done["analysis_id"], "user_alpha": None})
        self.assertEqual(response.status_code, 404)

    async def test_chat_trace_preserves_nested_calls_arguments_results_and_timing(self):
        response = await self.client.post("/chat", json={"message": TASK})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["contract_verified"])
        self.assertEqual(result["contract"], "provisional-modelmatch-chat-v1")
        calls = result["tool_calls"]
        self.assertEqual(len(calls), 6)
        self.assertEqual(len({c["call_id"] for c in calls}), 6)
        self.assertEqual(len({c["context_id"] for c in calls}), 4)
        for c in calls:
            self.assertEqual(c["status"], "completed")
            self.assertIsNotNone(c["result"])
            self.assertGreaterEqual(c["elapsed_seconds"], 0)
            self.assertLessEqual(c["started_at"], c["ended_at"])
        domain = next(c for c in calls if c["tool"] == "get_domain_evidence")
        self.assertEqual(domain["arguments"]["domain"], "finance")
        self.assertTrue(domain["agent"].startswith("Researcher B"))

    async def test_invalid_inputs_rejected_before_research(self):
        for body in ({"question": " " * 5}, {"question": TASK, "ttft": -1}, {"question": TASK, "user_alpha": True},
                     {"question": TASK, "monthly_budget": "100"}, {"question": TASK, "hard_constraints": ["ttft"]},
                     {"question": TASK, "unexpected": "field"}):
            self.assertEqual((await self.client.post("/api/modelmatch/analyze", json=body)).status_code, 422)
        self.assertEqual(self.service.active, 0)
        self.assertEqual(len(self.service.recent), 0)

    async def test_live_calls_require_explicit_approval_before_service_execution(self):
        with patch.dict(os.environ, {"MODELMATCH_OFFLINE": "0"}), patch.object(self.service, "run", new_callable=AsyncMock) as run:
            for path, body in (("/api/modelmatch/analyze", {"question": TASK}), ("/chat", {"message": TASK})):
                self.assertEqual((await self.client.post(path, json=body)).status_code, 403)
            run.assert_not_awaited()

    async def test_origin_and_body_limits_are_enforced(self):
        response = await self.client.post("/chat", json={"message": TASK}, headers={"Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)
        response = await self.client.post("/chat", content=b"x" * 16001, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)

    async def test_non_finite_and_invalid_json_never_reach_provider(self):
        for content in ('{"question":"Analyze documents","ttft":NaN}',
                        '{"question":"Analyze documents","ttft":1e999}', '{"question":'):
            response = await self.client.post("/chat", content=content, headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.service.recent), 0)

    async def test_researcher_failure_is_attributed_without_invented_completion(self):
        from offline_model import OfflineModel
        original = OfflineModel.get_response
        async def failing(model, system_instructions, *args, **kwargs):
            if "Inspect only requested operations" in system_instructions:
                raise RuntimeError("SIMULATED_SECRET")
            return await original(model, system_instructions, *args, **kwargs)
        with patch.object(OfflineModel, "get_response", failing):
            response = await self.client.post("/chat", json={"message": TASK})
        body = response.json()
        self.assertEqual(body["result"]["status"], "insufficient_evidence")
        self.assertNotIn("decision", body["result"])
        call = next(c for c in body["tool_calls"] if c["tool"] == "research_c")
        self.assertEqual(call["status"], "failed")
        self.assertNotIn("SIMULATED_SECRET", response.text)

    async def test_concurrency_and_request_rate_limits_are_bounded(self):
        self.service.active = 2
        self.assertEqual((await self.client.post("/chat", json={"message": TASK})).status_code, 429)
        self.service.active = 0
        import time
        self.service.recent.extend([time.monotonic()] * 6)
        self.assertEqual((await self.client.post("/chat", json={"message": TASK})).status_code, 429)

    async def test_unexpected_errors_are_sanitized_and_release_capacity(self):
        with patch.object(self.service, "run", new_callable=AsyncMock, side_effect=RuntimeError("SIMULATED_SECRET")):
            response = await self.client.post("/api/modelmatch/analyze", json={"question": TASK})
        self.assertNotIn("SIMULATED_SECRET", response.text)
        self.assertIn('"type": "error"', response.text)
        self.assertEqual(self.service.active, 0)

    async def test_disconnect_cancels_work_without_leaking_capacity(self):
        entered, cancelled = asyncio.Event(), asyncio.Event()
        async def wait(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        from fastapi import FastAPI
        from modelmatch_web import install_modelmatch
        isolated_app = FastAPI()
        router = install_modelmatch(isolated_app)
        isolated_service = isolated_app.state.modelmatch
        endpoint = next(r.endpoint for r in router.routes if getattr(r, "path", None) == "/api/modelmatch/analyze")
        with patch.object(isolated_service, "run", side_effect=wait):
            response = await endpoint(WebInput(question=TASK))
            await anext(response.body_iterator)
            await entered.wait()
            await response.body_iterator.aclose()
            await asyncio.wait_for(cancelled.wait(), 1)
        self.assertEqual(isolated_service.active, 0)

    async def test_frontend_fields_and_api_schema_share_the_same_names(self):
        from html.parser import HTMLParser
        class Fields(HTMLParser):
            def __init__(self):
                super().__init__()
                self.names = set()
            def handle_starttag(self, tag, attrs):
                if tag in ("input", "textarea"):
                    name = dict(attrs).get("name")
                    if name and name != "hard":
                        self.names.add(name)
        fields = Fields()
        root = Path(__file__).resolve().parents[1]
        fields.feed((root / "static/modelmatch.html").read_text())
        self.assertTrue(fields.names <= set(WebInput.model_fields))
        script = (root / "static/modelmatch.js").read_text()
        for status in ("fully_evaluable", "provisional", "unverified", "ineligible"):
            self.assertIn(status, script)
        for fragment in ("writer_explanation_stale", "recalculate(null)", "textContent", "AbortController", "TextDecoder"):
            self.assertIn(fragment, script)
        self.assertNotIn("innerHTML", script)


class EvidenceMemoryTests(unittest.TestCase):
    def test_capacity_ttl_and_oversized_records_are_bounded(self):
        service = AnalysisService()
        service.capacity = 1
        first = service.remember({"status": "test"}, None)
        second = service.remember({"status": "test"}, None)
        self.assertNotIn(first, service.saved)
        self.assertIn(second, service.saved)
        service.saved[second]["expires"] = 0
        service.prune()
        self.assertEqual(service.saved, {})
        service.max_saved_bytes = 32
        self.assertIsNone(service.remember({"large": "x" * 100}, None))
