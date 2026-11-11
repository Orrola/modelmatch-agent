"""Provider-free wiring checks, not evidence of successful live provider execution."""

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
import app as web
from modelmatch_web import AnalysisService, WebHooks, WebInput
from tools.artificial_analysis import AAError
from vertex_runtime import VertexConfig


TASK = "Analyze financial documents for a finance team."


class LiveWebWiringTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MODELMATCH_OFFLINE": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.service = web.app.state.modelmatch
        self.service.saved.clear()
        self.service.recent.clear()
        self.service.active = 0
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://local-wiring")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_unset_mode_defaults_to_live_without_contacting_providers(self):
        os.environ.pop("MODELMATCH_OFFLINE", None)
        with patch.object(self.service, "run", new_callable=AsyncMock) as run, \
             patch("vertex_runtime.create_models") as models, \
             patch("tools.artificial_analysis.ArtificialAnalysisClient.fetch_snapshot", new_callable=AsyncMock) as aa:
            for path in ("/modelmatch", "/modelmatch.js", "/modelmatch.css", "/healthz", "/api/modelmatch/config"):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 200)
            config = (await self.client.get("/api/modelmatch/config")).json()
            self.assertEqual(config["mode"], "live_vertex")
            self.assertFalse(config["grounding_enabled"])
            run.assert_not_awaited()
            models.assert_not_called()
            aa.assert_not_awaited()

    async def test_live_form_request_reaches_existing_sse_service_once(self):
        # This sentinel has no benchmark values and does not pretend to be a live recommendation.
        result = {"status": "clarification_needed", "questions": ["Specify the task."], "markdown": "Specify the task."}
        with patch.object(self.service, "run", new_callable=AsyncMock, return_value=(result, None)) as run:
            response = await self.client.post("/api/modelmatch/analyze", json={"question": TASK, "approve_live": True})
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[-1]["type"], "done")
        run.assert_awaited_once()
        request = run.call_args.args[0]
        self.assertEqual(request.question, TASK)
        self.assertTrue(request.approve_live)
        self.assertEqual(self.service.active, 0)

    async def test_live_branch_constructs_vertex_models_and_real_aa_loader(self):
        config = VertexConfig(project="ieor4570-yg3133", location="global")
        model, researcher = object(), object()
        service = AnalysisService()
        hooks = WebHooks(lambda event: None)
        workflow = SimpleNamespace(plan=None)
        factory = MagicMock(return_value=workflow)
        # Metadata-only sentinel: no models, scores or simulated evaluations.
        aa = AsyncMock(return_value={"data_mode": "live", "snapshot_id": "transport-wiring-only"})

        async def execute(prompt):
            self.assertEqual(prompt, TASK)
            loaded = await factory.call_args.kwargs["snapshot_loader"]()
            self.assertEqual(loaded["snapshot_id"], "transport-wiring-only")
            return {"status": "clarification_needed", "questions": ["Wiring sentinel."], "markdown": "Wiring sentinel."}

        workflow.run = AsyncMock(side_effect=execute)
        with patch("vertex_runtime.VertexConfig.from_environment", return_value=config) as environment, \
             patch("vertex_runtime.create_models", return_value=(model, researcher)) as models, \
             patch("modelmatch_web.WebWorkflow", factory), \
             patch("tools.artificial_analysis.ArtificialAnalysisClient.fetch_snapshot", aa), \
             patch("offline_model.OfflineModel", side_effect=AssertionError("Synthetic model must not be constructed.")):
            result, prepared = await service.run(WebInput(question=TASK, approve_live=True), hooks)
        environment.assert_called_once()
        models.assert_called_once()
        aa.assert_awaited_once()
        self.assertEqual(models.call_args.args[1].max_calls, 24)
        self.assertEqual(factory.call_args.args, (model, researcher))
        settings = factory.call_args.kwargs["settings"]
        self.assertEqual(settings.max_tokens, 2048)
        self.assertEqual(settings.extra_args["timeout"], 30)
        self.assertEqual(settings.extra_args["num_retries"], 0)
        self.assertNotIn("official_service", factory.call_args.kwargs)
        self.assertEqual(factory.call_args.kwargs["limits"].timeout_seconds, 180)
        self.assertEqual(result["execution_mode"], "live_vertex")
        self.assertIsNone(prepared)

    async def test_live_loader_rejects_synthetic_data_without_fallback(self):
        config = VertexConfig(project="ieor4570-yg3133")
        workflow = SimpleNamespace(plan=None)
        factory = MagicMock(return_value=workflow)
        async def execute(prompt):
            return await factory.call_args.kwargs["snapshot_loader"]()
        workflow.run = AsyncMock(side_effect=execute)
        with patch("vertex_runtime.VertexConfig.from_environment", return_value=config), \
             patch("vertex_runtime.create_models", return_value=(object(), object())), \
             patch("modelmatch_web.WebWorkflow", factory), \
             patch("tools.artificial_analysis.ArtificialAnalysisClient.fetch_snapshot", new_callable=AsyncMock,
                   return_value={"data_mode": "mock"}), \
             patch("offline_model.OfflineModel", side_effect=AssertionError("Synthetic fallback is forbidden.")):
            with self.assertRaisesRegex(AAError, "synthetic replacement"):
                await AnalysisService().run(WebInput(question=TASK, approve_live=True), WebHooks(lambda event: None))

    async def test_provider_setup_failure_does_not_construct_synthetic_model(self):
        with patch("vertex_runtime.VertexConfig.from_environment", return_value=VertexConfig(project="ieor4570-yg3133")), \
             patch("vertex_runtime.create_models", side_effect=RuntimeError("SIMULATED_SECRET")), \
             patch("offline_model.OfflineModel") as offline:
            response = await self.client.post("/api/modelmatch/analyze", json={"question": TASK, "approve_live": True})
        self.assertEqual(response.status_code, 200)
        self.assertIn("No synthetic results were substituted", response.text)
        self.assertNotIn("SIMULATED_SECRET", response.text)
        self.assertNotIn("Fictional", response.text)
        offline.assert_not_called()

    async def test_synthetic_mode_requires_explicit_setting(self):
        for value in ("", "0", "false", "true", "demo"):
            with patch.dict(os.environ, {"MODELMATCH_OFFLINE": value}):
                self.assertFalse(AnalysisService().offline)
        with patch.dict(os.environ, {"MODELMATCH_OFFLINE": "1"}):
            self.assertTrue(AnalysisService().offline)
