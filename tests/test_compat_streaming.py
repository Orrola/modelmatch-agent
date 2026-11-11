"""ModelMatch-only root and legacy GET SSE compatibility contracts."""

import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
import app as web


class CompatibilityStreamingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MODELMATCH_OFFLINE": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        service = web.app.state.modelmatch
        service.saved.clear()
        service.recent.clear()
        service.active = 0

    async def request(self, path, params=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://compat-test") as client:
            return await client.get(path, params=params)

    def events(self, response):
        return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]

    async def test_root_serves_modelmatch_instead_of_obsolete_product(self):
        response = await self.request("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ModelMatch AI", response.text)
        self.assertIn('id="view-comparison"', response.text)
        for path in ("/context", "/context-panel.js"):
            self.assertEqual((await self.request(path)).status_code, 404)

    async def test_modelmatch_get_sse_preserves_start_and_done_fields(self):
        response = await self.request("/run", {"question": "Analyze financial documents for a finance team.", "mode": "modelmatch"})
        self.assertEqual(response.status_code, 200)
        events = self.events(response)
        self.assertEqual(events[0]["type"], "start")
        self.assertTrue(events[0]["run_id"])
        done = events[-1]
        self.assertEqual(done["type"], "done")
        self.assertEqual(done["markdown"], done["result"]["markdown"])
        self.assertIn("decision", done["result"])
        self.assertTrue(any(e["type"] == "tool_trace" for e in events))

    async def test_default_get_research_is_modelmatch_and_clarification_is_preserved(self):
        response = await self.request("/run", {"question": "help"})
        done = self.events(response)[-1]
        self.assertEqual(done["result"]["status"], "clarification_needed")
        self.assertEqual(done["markdown"], done["result"]["markdown"])

    async def test_unknown_and_removed_modes_are_rejected_before_execution(self):
        for mode in ("unknown", "wikipedia"):
            response = await self.request("/run", {"question": "Analyze documents", "mode": mode})
            self.assertEqual(response.status_code, 422)

    async def test_get_errors_are_sanitized(self):
        with patch.object(web.app.state.modelmatch, "run", new_callable=AsyncMock, side_effect=RuntimeError("SIMULATED_SECRET")):
            response = await self.request("/run", {"question": "Analyze documents"})
        self.assertEqual(self.events(response)[-1]["type"], "error")
        self.assertNotIn("SIMULATED_SECRET", response.text)

    async def test_writer_failure_flags_are_not_hidden_by_compatibility_adapter(self):
        result = {"status": "provisional", "markdown": "Deterministic fallback, not live Writer success.",
                  "writer_fallback": True, "trace": [{"type": "writer_rejected", "agent": "Writer"}]}
        with patch.object(web.app.state.modelmatch, "run", new_callable=AsyncMock, return_value=(result, None)):
            response = await self.request("/run", {"question": "Analyze documents"})
        done = self.events(response)[-1]
        self.assertTrue(done["result"]["writer_fallback"])
        self.assertEqual(done["result"]["trace"][0]["type"], "writer_rejected")

    async def test_closing_get_stream_cancels_shared_worker(self):
        entered, cancelled = asyncio.Event(), asyncio.Event()
        async def wait(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        with patch.object(web.app.state.modelmatch, "run", side_effect=wait):
            response = await web.run("Analyze documents")
            await anext(response.body_iterator)
            await entered.wait()
            await response.body_iterator.aclose()
            await asyncio.wait_for(cancelled.wait(), 1)
        self.assertEqual(web.app.state.modelmatch.active, 0)
