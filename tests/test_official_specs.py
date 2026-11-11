"""Offline fixtures for grounding citations, official pages and unknown handling."""

import asyncio
import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import httpx

from tools.artificial_analysis import load_mock_snapshot
from tools.model_evidence import OperationalRequirement, RelevanceDecision, build_candidates
from tools.official_specs import OfficialSpecService, SpecEvidence, SpecRequest, fetch_official_page

URL = "https://docs.cloud.google.com/test-only-model-specification"
EXCERPT = "gemini-test-001 context window 100000 tokens."


class FixtureGrounding:
    is_live = False

    def __init__(self):
        self.claims = [{"metric": "context_window", "value": 100000, "exact_version": "gemini-test-001", "source_url": URL, "excerpt": EXCERPT}]
        self.support = True
        self.queries = ["synthetic official-spec protocol test"]
        self.calls = 0

    async def search(self, prompt):
        self.calls += 1
        text = json.dumps({"claims": self.claims})
        return {"text": text, "metadata": {"grounding_chunks": [{"web": {"uri": URL}}],
            "grounding_supports": [{"segment": {"text": text}, "grounding_chunk_indices": [0]}] if self.support else [],
            "web_search_queries": self.queries, "search_entry_point": {"rendered_content": "<div>Offline fixture</div>"}},
            "usage": {"prompt_token_count": 1, "candidates_token_count": 1}}


class OfficialSpecsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.backend = FixtureGrounding()
        self.page = {"url": URL, "text": EXCERPT, "source_date": datetime.now(timezone.utc).date().isoformat()}
        self.fetcher = AsyncMock(side_effect=lambda *args: dict(self.page))
        self.request = SpecRequest("synthetic-finance", "Synthetic protocol model", "gemini-test-001", "Google", "mock-protocol-only", ("context_window",))

    def service(self, **kwargs):
        return OfficialSpecService(self.backend, fetcher=self.fetcher, **kwargs)

    async def test_grounded_exact_official_excerpt_is_verified_as_fixture_only(self):
        service = self.service()
        result = await service.lookup(self.request)
        record = result["records"]["context_window"]
        self.assertEqual(record["verification_status"], "verified")
        self.assertEqual(record["verification_mode"], "offline_fixture")
        self.assertEqual(record["value"], 100000)
        self.assertEqual(record["source_url"], URL)
        self.assertEqual(record["excerpt"], EXCERPT)
        self.assertEqual(result["grounding_metadata"]["search_entry_point"]["rendered_content"], "<div>Offline fixture</div>")

    async def test_missing_citation_support_is_unknown(self):
        self.backend.support = False
        result = await self.service().lookup(self.request)
        self.assertEqual(result["records"]["context_window"]["verification_status"], "unknown")
        self.fetcher.assert_not_awaited()

    async def test_wrong_version_or_variant_is_unknown(self):
        self.backend.claims[0]["exact_version"] = "gemini-test-001-lite"
        result = await self.service().lookup(self.request)
        self.assertIsNone(result["records"]["context_window"]["value"])

    async def test_unquoted_or_wrong_value_is_unknown(self):
        self.backend.claims[0]["value"] = 200000
        result = await self.service().lookup(self.request)
        self.assertIsNone(result["records"]["context_window"]["value"])

    async def test_excerpt_not_on_page_is_unknown(self):
        self.page["text"] = "Unrelated official documentation."
        result = await self.service().lookup(self.request)
        self.assertIsNone(result["records"]["context_window"]["value"])

    async def test_deprecated_excerpt_does_not_become_verified(self):
        self.backend.claims[0]["excerpt"] += " This model is deprecated."
        self.page["text"] = self.backend.claims[0]["excerpt"]
        result = await self.service().lookup(self.request)
        self.assertIsNone(result["records"]["context_window"]["value"])

    async def test_stale_undated_and_future_sources_are_unknown(self):
        for date in (None, "2020-01-01", (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()):
            self.page["source_date"] = date
            result = await self.service().lookup(self.request)
            self.assertEqual(result["records"]["context_window"]["verification_status"], "unknown")

    async def test_third_party_source_is_unknown(self):
        self.page["url"] = "https://third-party.example/model"
        result = await self.service().lookup(self.request)
        self.assertIsNone(result["records"]["context_window"]["value"])

    async def test_conflicting_values_are_not_averaged(self):
        second = {**self.backend.claims[0], "value": 200000, "excerpt": "gemini-test-001 context window 200000 tokens."}
        self.backend.claims.append(second)
        self.page["text"] += " " + second["excerpt"]
        result = await self.service().lookup(self.request)
        self.assertEqual(result["records"]["context_window"]["reason"], "conflicting_official_values")

    async def test_no_requirement_or_unconfigured_provider_does_not_search(self):
        for request in (SpecRequest("id", "name", "slug", "Google", "snapshot", ()),
                        SpecRequest("id", "name", "slug", "Unconfigured", "snapshot", ("context_window",))):
            await self.service().lookup(request)
        self.assertEqual(self.backend.calls, 0)

    async def test_live_search_requires_explicit_opt_in(self):
        self.backend.is_live = True
        result = await self.service().lookup(self.request)
        self.assertEqual(result["records"]["context_window"]["reason"], "live_lookup_not_approved")
        self.assertEqual(self.backend.calls, 0)

    async def test_cache_and_concurrent_requests_do_not_duplicate_search(self):
        service = self.service()
        results = await asyncio.gather(service.lookup(self.request), service.lookup(self.request))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.backend.calls, 1)

    async def test_candidate_request_and_reported_query_limits(self):
        service = self.service(max_candidates=1, max_grounding_calls=1)
        await service.lookup(self.request)
        other = SpecRequest("other-id", "Other", "other", "Google", "snapshot", ("context_window",))
        result = await service.lookup(other)
        self.assertEqual(result["records"]["context_window"]["reason"], "grounding_budget_exhausted")
        self.backend.queries = ["query"] * 5
        result = await self.service().lookup(self.request)
        self.assertEqual(result["records"]["context_window"]["reason"], "provider_search_query_budget_exceeded")

    async def test_errors_are_sanitized_without_benchmark_fallback(self):
        self.backend.search = AsyncMock(side_effect=RuntimeError("SIMULATED_SECRET"))
        service = self.service()
        result = await service.lookup(self.request)
        self.assertIsNone(result["records"]["context_window"]["value"])
        self.assertNotIn("SIMULATED_SECRET", json.dumps(service.telemetry))

    async def test_official_records_resolve_only_bound_ids_and_requirements(self):
        report = await self.service().lookup(self.request)
        evidence = SpecEvidence(**report["records"]["context_window"])
        snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        relevance = RelevanceDecision("Synthetic financial task", "finance", "strong", "Offline mapping only.")
        prepared = build_candidates(snapshot, relevance, (OperationalRequirement("context_window", 50000, hard=True),),
                                    official_evidence={"synthetic-finance": {"context_window": evidence}})
        self.assertEqual(prepared["candidates"]["synthetic-finance"]["eligibility"], "eligible")
        self.assertEqual(prepared["candidates"]["synthetic-engineering"]["eligibility"], "unverified")
        self.assertTrue(any(e["supporting_excerpt"] == EXCERPT for e in prepared["evidence"].values()))
        too_large = build_candidates(snapshot, relevance, (OperationalRequirement("context_window", 200000, hard=True),),
                                    official_evidence={"synthetic-finance": {"context_window": evidence}})
        self.assertEqual(too_large["candidates"]["synthetic-finance"]["eligibility"], "ineligible")

    async def test_official_fetch_rejects_ssrf_and_open_redirects(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        transport = httpx.MockTransport(handler)
        for url in ("http://127.0.0.1/private", "https://docs.cloud.google.com.evil.example/spec"):
            with self.assertRaises(ValueError):
                await fetch_official_page(url, ("docs.cloud.google.com",), transport=transport)
        self.assertEqual(calls, [])
        with self.assertRaises(ValueError):
            await fetch_official_page(URL, ("docs.cloud.google.com",), transport=transport)
        self.assertEqual(len(calls), 1)

    async def test_html_source_excludes_hidden_scripts_and_keeps_date(self):
        html = f'<h1>{EXCERPT}</h1><script>secret fake limit</script><p>Last updated 2026-11-10</p>'
        page = await fetch_official_page(URL, ("docs.cloud.google.com",),
                                        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=html)))
        self.assertNotIn("secret fake limit", page["text"])
        self.assertEqual(page["source_date"], "2026-11-10")
