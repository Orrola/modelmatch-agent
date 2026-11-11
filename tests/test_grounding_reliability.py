"""Offline regressions for real malformed output and synthetic SDK responses."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from google.genai import types

from tests.test_official_specs import EXCERPT, URL, FixtureGrounding
from tools.official_specs import OfficialSpecService, SpecRequest, VertexGroundingBackend, discovery_prompt
from vertex_runtime import CallBudget, VertexConfig


class GroundingReliabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request = SpecRequest("test-only-id", "Synthetic protocol model", "gemini-test-001", "Google",
                                   "offline-only-snapshot", ("context_window",))
        self.backend = FixtureGrounding()
        from datetime import datetime, timezone
        self.page = {"url": URL, "text": EXCERPT, "source_date": datetime.now(timezone.utc).date().isoformat()}
        self.fetcher = AsyncMock(return_value=self.page)

    async def lookup(self, response=None):
        if response is not None:
            self.backend.search = AsyncMock(return_value=response)
        self.service = OfficialSpecService(self.backend, fetcher=self.fetcher)
        return await self.service.lookup(self.request)

    async def synthetic_response(self, finish="STOP"):
        response = await self.backend.search("Offline fixture.")
        response["diagnostics"] = {"model_version": "synthetic-version", "candidates": [
            {"index": 0, "finish_reason": finish, "finish_message": None}],
            "request": {"max_output_tokens": 1024}}
        return response

    async def test_historical_non_json_is_not_reclassified_as_proven_truncation(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/grounding_non_json_live.json").read_text())
        result = await self.lookup(fixture["response"])
        diagnostics = result["diagnostics"]
        self.assertEqual(diagnostics["primary_failure"], "malformed_json")
        self.assertIn("missing_grounding_citations", diagnostics["failure_classifications"])
        self.assertNotIn("incomplete_generation", diagnostics["failure_classifications"])
        self.assertIn("finish_reason_unavailable", diagnostics["warnings"])
        self.assertEqual(diagnostics["generation"], {})
        self.assertEqual(diagnostics["usage"]["thoughts_token_count"], 1562)
        self.assertEqual(diagnostics["usage"]["candidates_token_count"], 38)
        self.assertEqual(diagnostics["visible_text"], fixture["response"]["text"])
        self.assertIsNone(result["records"]["context_window"]["value"])
        self.backend.search.assert_awaited_once()
        self.fetcher.assert_not_awaited()

    async def test_incomplete_generation_never_verifies_even_valid_json(self):
        for finish in ("MAX_TOKENS", "SAFETY", "OTHER"):
            result = await self.lookup(await self.synthetic_response(finish))
            self.assertEqual(result["records"]["context_window"]["reason"], "incomplete_generation")
            self.assertIsNone(result["records"]["context_window"]["value"])
        self.fetcher.assert_not_awaited()

    async def test_missing_finish_reason_stays_missing_without_assuming_stop(self):
        result = await self.lookup(await self.synthetic_response(None))
        self.assertIsNone(result["diagnostics"]["generation"]["candidates"][0]["finish_reason"])
        self.assertIn("finish_reason_unavailable", result["diagnostics"]["warnings"])
        # Complete official evidence can be verified independently of unknown stop metadata.
        self.assertEqual(result["records"]["context_window"]["verification_status"], "verified")

    async def test_unexpected_usage_is_preserved_without_inventing_truncation(self):
        response = await self.synthetic_response()
        response["usage"] = {"prompt_token_count": 202, "candidates_token_count": 38,
                             "thoughts_token_count": 1562, "total_token_count": 1802}
        result = await self.lookup(response)
        self.assertEqual(result["diagnostics"]["usage"], response["usage"])
        self.assertIn("reported_output_plus_thoughts_exceeds_configured_max", result["diagnostics"]["warnings"])
        self.assertNotIn("incomplete_generation", result["diagnostics"]["failure_classifications"])

    async def test_valid_json_without_citations_is_unknown(self):
        response = await self.synthetic_response()
        response["metadata"] = {"web_search_queries": ["offline query"]}
        result = await self.lookup(response)
        self.assertEqual(result["records"]["context_window"]["reason"], "missing_grounding_citations")
        self.fetcher.assert_not_awaited()

    async def test_invalid_citation_segments_do_not_trigger_source_fetches(self):
        response = await self.synthetic_response()
        response["metadata"]["grounding_supports"][0]["segment"]["text"] = "Not in the generated response."
        result = await self.lookup(response)
        self.assertEqual(result["records"]["context_window"]["reason"], "missing_grounding_citations")
        self.fetcher.assert_not_awaited()

    async def test_official_source_fetch_failure_is_distinct_and_sanitized(self):
        self.fetcher.side_effect = RuntimeError("SIMULATED_SECRET")
        result = await self.lookup(await self.synthetic_response())
        self.assertEqual(result["records"]["context_window"]["reason"], "official_source_unavailable")
        self.assertNotIn("SIMULATED_SECRET", json.dumps(result))

    async def test_official_domain_spoof_cannot_be_verified(self):
        self.page["url"] = "https://docs.cloud.google.com.evil.example/spec"
        result = await self.lookup(await self.synthetic_response())
        self.assertEqual(result["records"]["context_window"]["reason"], "unverified_specification")
        self.assertIsNone(result["records"]["context_window"]["value"])

    async def test_exact_version_mismatch_has_its_own_classification(self):
        self.backend.claims[0]["exact_version"] = "gemini-test-001-lite"
        result = await self.lookup(await self.synthetic_response())
        self.assertEqual(result["records"]["context_window"]["reason"], "version_mismatch")
        self.assertEqual(result["diagnostics"]["metric_failures"]["context_window"], "version_mismatch")

    async def test_malformed_and_non_object_json_are_rejected_without_repair(self):
        for text in ('{"claims":', "[]", "null", '{"claims": {}, "extra": 1}'):
            response = await self.synthetic_response()
            response["text"] = text
            result = await self.lookup(response)
            self.assertIsNone(result["records"]["context_window"]["value"])
            self.assertIn(result["records"]["context_window"]["reason"], ("malformed_json", "invalid_claim_structure"))
        self.fetcher.assert_not_awaited()

    async def test_well_formed_json_with_unverified_excerpt_is_unknown(self):
        self.page["text"] = "Unrelated official page."
        result = await self.lookup(await self.synthetic_response())
        self.assertEqual(result["records"]["context_window"]["reason"], "unverified_specification")

    async def test_explicit_empty_claims_does_not_invent_values(self):
        self.backend.claims = []
        result = await self.lookup(await self.synthetic_response())
        self.assertIsNone(result["records"]["context_window"]["value"])
        self.fetcher.assert_not_awaited()

    async def test_discovery_prompt_defines_limits_and_valid_empty_json(self):
        prompt = discovery_prompt(self.request, ("docs.cloud.google.com",), self.request.metrics)
        self.assertIn('{"claims": []}', prompt)
        self.assertIn("combined input-plus-output", prompt)
        self.assertIn("never infer", prompt)
        self.assertIn(self.request.model_slug, prompt)
        self.assertIn("Python independently checks", prompt)

    async def test_backend_retains_diagnostics_and_supported_low_thinking(self):
        response = types.GenerateContentResponse(model_version="synthetic-version", candidates=[types.Candidate(
            index=0, finish_reason=types.FinishReason.MAX_TOKENS, finish_message="Stopped. Bearer secret-value",
            content=types.Content(parts=[types.Part(text='{"claims":')]),
            grounding_metadata=types.GroundingMetadata(web_search_queries=["offline query"]))],
            usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=202,
                candidates_token_count=38, thoughts_token_count=1562, total_token_count=1802))
        models = SimpleNamespace(generate_content=AsyncMock(return_value=response))
        client = MagicMock()
        client.aio.__aenter__ = AsyncMock(return_value=SimpleNamespace(models=models))
        client.aio.__aexit__ = AsyncMock(return_value=False)
        budget = CallBudget(max_calls=1)
        config = VertexConfig(project="existing-project")
        with patch("google.genai.Client", return_value=client) as factory:
            result = await VertexGroundingBackend(config, budget).search("Offline fixture.")
        generation = models.generate_content.call_args.kwargs["config"]
        self.assertEqual(generation.thinking_config.thinking_level, types.ThinkingLevel.LOW)
        self.assertIsNone(generation.thinking_config.thinking_budget)
        self.assertEqual(generation.max_output_tokens, 1024)
        self.assertIsNone(generation.response_mime_type)
        self.assertIsNone(generation.response_schema)
        self.assertEqual(len(generation.tools), 1)
        self.assertIsNotNone(generation.tools[0].google_search)
        self.assertIsNone(generation.tools[0].function_declarations)
        self.assertEqual(factory.call_args.kwargs["http_options"].retry_options.attempts, 1)
        self.assertEqual(budget.calls, 1)
        self.assertEqual(result["diagnostics"]["model_version"], "synthetic-version")
        candidate = result["diagnostics"]["candidates"][0]
        self.assertEqual(candidate["finish_reason"], "MAX_TOKENS")
        self.assertNotIn("secret-value", candidate["finish_message"])
        self.assertEqual(result["usage"]["thoughts_token_count"], 1562)
        self.assertEqual(result["metadata"]["web_search_queries"], ["offline query"])

    async def test_unconfirmed_model_does_not_inherit_thinking_settings(self):
        models = SimpleNamespace(generate_content=AsyncMock(return_value=SimpleNamespace(
            text='{"claims":[]}', candidates=[], usage_metadata=None)))
        client = MagicMock()
        client.aio.__aenter__ = AsyncMock(return_value=SimpleNamespace(models=models))
        client.aio.__aexit__ = AsyncMock(return_value=False)
        config = replace(VertexConfig(project="existing-project"), grounding_model="gemini-offline-test")
        with patch("google.genai.Client", return_value=client):
            result = await VertexGroundingBackend(config, CallBudget(max_calls=1)).search("Offline only.")
        self.assertIsNone(models.generate_content.call_args.kwargs["config"].thinking_config)
        self.assertIsNone(result["diagnostics"]["model_version"])
        self.assertEqual(result["diagnostics"]["candidates"], [])
