"""Offline provider configuration, billing gates and call-meter tests."""

import asyncio
import contextlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from agents import ModelSettings
from agents.usage import Usage

from scripts.vertex_smoke import main
from vertex_runtime import BudgetExceeded, CallBudget, MeteredModel, VertexConfig, safe_error
from tools.official_specs import VertexGroundingBackend


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = VertexConfig("synthetic-project", max_output_tokens=128)

    async def test_call_budget_usage_and_output_limit(self):
        inner = SimpleNamespace(get_response=AsyncMock(return_value=SimpleNamespace(usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7), output=[])))
        budget = CallBudget(max_calls=1)
        model = MeteredModel(inner, "gemini-test", budget, self.config)
        args = (None, "ping", ModelSettings(max_tokens=4000), [], None, [], None)
        await model.get_response(*args)
        with self.assertRaises(BudgetExceeded):
            await model.get_response(*args)
        inner.get_response.assert_awaited_once()
        self.assertEqual(inner.get_response.call_args.args[2].max_tokens, 128)
        self.assertEqual(inner.get_response.call_args.args[2].extra_args["num_retries"], 0)
        self.assertEqual(budget.records[0]["usage"]["total_tokens"], 7)
        self.assertNotIn("provider_response", budget.records[0])

    async def test_smoke_response_capture_omits_headers_and_reasoning(self):
        response = SimpleNamespace(usage=Usage(), response_id="offline-response", request_id=None,
            headers={"Authorization": "SIMULATED_SECRET"},
            output=[SimpleNamespace(type="message", role="assistant", content=[SimpleNamespace(text="OK")]),
                    SimpleNamespace(type="reasoning", text="PRIVATE_REASONING")])
        budget = CallBudget(max_calls=1, capture_responses=True)
        model = MeteredModel(SimpleNamespace(get_response=AsyncMock(return_value=response)), "gemini-test", budget, self.config)
        await model.get_response(None, "ping", ModelSettings(), [], None, [], None)
        captured = budget.records[0]["provider_response"]
        self.assertEqual(captured["output"], [{"type": "message", "role": "assistant", "text": "OK"}])
        self.assertNotIn("SIMULATED_SECRET", json.dumps(budget.records))
        self.assertNotIn("PRIVATE_REASONING", json.dumps(budget.records))

    async def test_prompt_budget_blocks_before_request(self):
        inner = SimpleNamespace(get_response=AsyncMock())
        model = MeteredModel(inner, "gemini-test", CallBudget(max_prompt_chars=10), self.config)
        with self.assertRaises(BudgetExceeded):
            await model.get_response(None, "x" * 100, ModelSettings(), [], None, [], None)
        inner.get_response.assert_not_awaited()

    async def test_timeout_and_error_sanitization(self):
        async def delayed(*args, **kwargs):
            await asyncio.sleep(1)
        config = VertexConfig("synthetic-project", timeout_seconds=0.01)
        budget = CallBudget(max_calls=1)
        model = MeteredModel(SimpleNamespace(get_response=delayed), "gemini-test", budget, config)
        with self.assertRaises(TimeoutError):
            await model.get_response(None, "ping", ModelSettings(), [], None, [], None)
        self.assertEqual(budget.records[0]["error"]["category"], "request_timeout")
        self.assertNotIn("SIMULATED_SECRET", json.dumps(safe_error(RuntimeError("SIMULATED_SECRET"))))

    async def test_live_modes_require_opt_in_and_extra_approval(self):
        for argv in (["--mode", "connectivity"], ["--mode", "pipeline", "--live"], ["--mode", "structured", "--live"], ["--mode", "grounding", "--live", "--approve-billable"]):
            with patch("scripts.vertex_smoke.create_models") as models, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                main(argv)
            self.assertEqual(caught.exception.code, 2)
            models.assert_not_called()

    async def test_existing_adc_configuration_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            config = VertexConfig.from_environment(diagnostics={"gcloud_project": "existing-project", "gcloud_region": None})
        self.assertEqual(config.project, "existing-project")
        self.assertEqual(config.location, "global")
        self.assertEqual(config.model, "gemini-3.5-flash")
        self.assertNotIn("api_key", config.__dict__)
        self.assertEqual(config.settings().extra_args["vertex_project"], "existing-project")

    async def test_real_sdk_workflow_uses_metered_model_without_provider(self):
        from pathlib import Path
        from unittest.mock import AsyncMock
        from orchestration import ModelMatchWorkflow
        from tests.fake_modelmatch import ScriptedModel, USER_INPUT
        from tools.artificial_analysis import load_mock_snapshot
        snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        budget = CallBudget(max_calls=24)
        model = MeteredModel(ScriptedModel(), "gemini-offline-test", budget, self.config)
        result = await ModelMatchWorkflow(model, model, settings=self.config.settings(), snapshot_loader=AsyncMock(return_value=snapshot)).run(USER_INPUT)
        self.assertEqual(result["status"], "supported", result.get("error"))
        self.assertEqual(budget.calls, 11)
        self.assertEqual(len(budget.records), 11)
        self.assertTrue(all(record["status"] == "success" for record in budget.records))

    async def test_grounding_backend_uses_separate_search_only_vertex_request(self):
        response = SimpleNamespace(text='{"claims":[]}', candidates=[], usage_metadata=None)
        models = SimpleNamespace(generate_content=AsyncMock(return_value=response))
        client = MagicMock()
        client.aio.__aenter__ = AsyncMock(return_value=SimpleNamespace(models=models))
        client.aio.__aexit__ = AsyncMock(return_value=False)
        with patch("google.genai.Client", return_value=client) as factory:
            result = await VertexGroundingBackend(self.config, CallBudget(max_calls=1)).search("One synthetic query.")
        self.assertEqual(result["text"], '{"claims":[]}')
        self.assertTrue(factory.call_args.kwargs["vertexai"])
        self.assertNotIn("api_key", factory.call_args.kwargs)
        config = models.generate_content.call_args.kwargs["config"]
        self.assertEqual(len(config.tools), 1)
        self.assertIsNotNone(config.tools[0].google_search)
        self.assertIsNone(config.tools[0].function_declarations)
        self.assertIsNone(config.response_schema)
        self.assertEqual(factory.call_args.kwargs["http_options"].retry_options.attempts, 1)
