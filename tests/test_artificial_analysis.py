"""Offline-only tests: MockTransport never calls the internet or reads .env."""

import asyncio
import copy
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from tools.artificial_analysis import (
    AAError, ArtificialAnalysisClient, audit_snapshot, load_mock_snapshot,
)
from scripts import aa_poc

FIXTURE = Path(__file__).parent / "fixtures/aa_free_mock.json"


class ClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pages = json.loads(FIXTURE.read_text())["pages"]
        self.calls = []

    def handler(self, request):
        self.calls.append(request)
        return httpx.Response(200, json=self.pages[int(request.url.params["page"]) - 1])

    def client(self, handler=None, **kwargs):
        return ArtificialAnalysisClient(
            "offline-test-secret", transport=httpx.MockTransport(handler or self.handler), **kwargs
        )

    async def test_async_pagination_and_auth(self):
        snapshot = await self.client().fetch_snapshot()
        self.assertEqual(len(snapshot["pages"]), 2)
        self.assertEqual([r.url.params["page"] for r in self.calls], ["1", "2"])
        self.assertTrue(all(r.headers["x-api-key"] == "offline-test-secret" for r in self.calls))
        self.assertTrue(all("offline-test-secret" not in str(r.url) for r in self.calls))
        self.assertTrue(snapshot["complete"])
        self.assertEqual(snapshot["requests_this_run"], 2)

    async def test_page_cap_marks_partial(self):
        snapshot = await self.client().fetch_snapshot(max_pages=1)
        self.assertFalse(snapshot["complete"])
        self.assertEqual(len(self.calls), 1)

    async def test_missing_key_no_network(self):
        client = self.client()
        client._api_key = ""
        with self.assertRaisesRegex(AAError, "AA_API_KEY is missing"):
            await client.fetch_snapshot()
        self.assertEqual(self.calls, [])

    async def test_timeout_retries_bounded_and_redacted(self):
        attempts = []
        def timeout(request):
            attempts.append(1)
            raise httpx.ReadTimeout("offline-test-secret", request=request)
        with patch("tools.artificial_analysis.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(AAError) as caught:
                await self.client(timeout).fetch_snapshot()
        self.assertEqual(len(attempts), 3)
        self.assertNotIn("offline-test-secret", str(caught.exception))

    async def test_http_errors_never_echo_response_body(self):
        for status in (401, 403, 400, 302):
            with self.subTest(status=status):
                def error(request):
                    return httpx.Response(status, text="offline-test-secret")
                with self.assertRaises(AAError) as caught:
                    await self.client(error).fetch_snapshot()
                self.assertIn(str(status), str(caught.exception))
                self.assertNotIn("offline-test-secret", str(caught.exception))

    async def test_short_429_wait_then_success(self):
        attempts = []
        def handler(request):
            attempts.append(1)
            if len(attempts) == 1:
                return httpx.Response(429, headers={"Retry-After": "1"})
            return self.handler(request)
        with patch("tools.artificial_analysis.asyncio.sleep", new_callable=AsyncMock) as sleep:
            snapshot = await self.client(handler).fetch_snapshot()
        sleep.assert_awaited_once_with(1)
        self.assertTrue(snapshot["complete"])
        self.assertEqual(snapshot["requests_this_run"], 3)

    async def test_long_429_does_not_sleep_or_retry(self):
        attempts = []
        def handler(request):
            attempts.append(1)
            return httpx.Response(429, headers={"Retry-After": "86400"})
        with patch("tools.artificial_analysis.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaisesRegex(AAError, "wait budget"):
                await self.client(handler).fetch_snapshot()
        self.assertEqual(len(attempts), 1)
        sleep.assert_not_awaited()

    async def test_5xx_bounded_retries(self):
        attempts = []
        def handler(request):
            attempts.append(1)
            return httpx.Response(503)
        with patch("tools.artificial_analysis.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaisesRegex(AAError, "retries exhausted"):
                await self.client(handler).fetch_snapshot()
        self.assertEqual(len(attempts), 3)

    async def test_schema_rejection(self):
        bodies = [[], {"data": []}, {**self.pages[0], "pagination": {"page": 1, "has_more": "yes"}}]
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaisesRegex(AAError, "schema error"):
                    await self.client(lambda r: httpx.Response(200, json=body)).fetch_snapshot()

    async def test_invalid_json(self):
        with self.assertRaisesRegex(AAError, "invalid JSON"):
            await self.client(lambda r: httpx.Response(200, text="invalid")).fetch_snapshot()

    async def test_index_version_conflict(self):
        self.pages[1]["intelligence_index_version"] = "different-mock-version"
        with self.assertRaisesRegex(AAError, "version changed"):
            await self.client().fetch_snapshot()

    async def test_duplicate_model_ids(self):
        self.pages[1]["data"][0]["id"] = "mock-model-a"
        with self.assertRaisesRegex(AAError, "duplicate model IDs"):
            await self.client().fetch_snapshot()

    async def test_cache_hit_refresh_and_no_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(cache_dir=Path(directory))
            first = await client.fetch_snapshot()
            second = await client.fetch_snapshot()
            self.assertTrue(second["cache_hit"])
            self.assertEqual(second["requests_this_run"], 0)
            self.assertEqual(first["snapshot_id"], second["snapshot_id"])
            self.assertEqual(len(self.calls), 2)
            raw = (Path(directory) / "aa-free-snapshot.json").read_text()
            self.assertNotIn("offline-test-secret", raw)
            self.assertNotIn("x-api-key", raw)
            await client.fetch_snapshot(refresh=True)
            self.assertEqual(len(self.calls), 4)

    async def test_expired_or_corrupt_cache_refetches(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(cache_dir=Path(directory), cache_ttl=0)
            await client.fetch_snapshot()
            await client.fetch_snapshot()
            self.assertEqual(len(self.calls), 4)
            (Path(directory) / "aa-free-snapshot.json").write_text("invalid")
            await client.fetch_snapshot()
            self.assertEqual(len(self.calls), 6)

    async def test_partial_cache_does_not_block_complete_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(cache_dir=Path(directory))
            await client.fetch_snapshot(max_pages=1)
            snapshot = await client.fetch_snapshot(max_pages=10)
            self.assertTrue(snapshot["complete"])
            self.assertFalse(snapshot["cache_hit"])
            self.assertEqual(len(self.calls), 3)

    async def test_timeout_is_configured_on_requests(self):
        await self.client(timeout=7).fetch_snapshot()
        self.assertEqual(self.calls[0].extensions["timeout"]["read"], 7)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_mock_snapshot(FIXTURE)

    def test_mock_is_explicit_and_all_benchmarks_null(self):
        self.assertEqual(self.snapshot["data_mode"], "mock")
        self.assertIsNone(self.snapshot["retrieved_at"])
        for page in self.snapshot["pages"]:
            for row in page["data"]:
                self.assertTrue(all(v is None for v in row["evaluations"].values()))

    def test_missing_null_invalid_and_zero_are_separate(self):
        result = audit_snapshot(self.snapshot)
        self.assertEqual(result["model_count"], 2)
        general = result["coverage"]["General Intelligence"]
        self.assertEqual(general["null"], 2)
        finance = result["coverage"]["finance_and_accounting_index"]
        self.assertEqual((finance["null"], finance["absent"]), (1, 1))
        self.assertEqual(result["coverage"]["Input price (USD / 1M tokens)"]["numeric"], 1)
        self.assertEqual(result["coverage"]["Output price (USD / 1M tokens)"]["invalid"], 1)

    def test_schema_includes_second_page_and_legacy_v3_separate(self):
        result = audit_snapshot(self.snapshot)
        self.assertIn("$.data[].second_page_only_field", result["schema"])
        self.assertIn("Legacy TTFT (median seconds)", result["coverage"])
        self.assertIn("v3 TTFT (mean seconds)", result["coverage"])
        self.assertTrue(all(n == 0 for n in result["joint_coverage"].values()))
        self.assertEqual(len(result["candidate_pool"]), 2)

    def test_bool_is_not_numeric(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["pages"][0]["data"][0]["pricing"]["price_1m_input_tokens"] = True
        result = audit_snapshot(snapshot)
        self.assertEqual(result["coverage"]["Input price (USD / 1M tokens)"]["invalid"], 1)

    def test_empty_data_is_auditable(self):
        snapshot = copy.deepcopy(self.snapshot)
        for page in snapshot["pages"]:
            page["data"] = []
        result = audit_snapshot(snapshot)
        self.assertEqual(result["model_count"], 0)
        self.assertEqual(result["candidate_pool"], [])

    def test_report_labels_mock_and_separates_metrics(self):
        text = aa_poc.report(self.snapshot, audit_snapshot(self.snapshot))
        self.assertIn("MOCK", text)
        self.assertIn("NOT real evaluations", text)
        self.assertIn("Legacy performance uses medians", text)
        self.assertIn("performance_v3 uses means", text)
        self.assertIn("$.data[].second_page_only_field", text)


class CLITests(unittest.IsolatedAsyncioTestCase):
    def args(self, **overrides):
        values = dict(mode="live", output=None, fixture=FIXTURE,
                      cache_ttl=3600, use_cache=False, max_pages=10)
        return Namespace(**(values | overrides))

    async def test_mock_cannot_overwrite_live_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(aa_poc, "ROOT", root), patch("builtins.print"):
                status = await aa_poc.run(self.args(mode="mock", output=root / "docs/aa-data-audit.md"))
            self.assertEqual(status, 2)
            self.assertFalse((root / "docs/aa-data-audit.md").exists())

    async def test_live_failure_preserves_previous_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "docs/aa-data-audit.md"
            output.parent.mkdir()
            output.write_text("previous real audit")
            with patch.object(aa_poc, "ROOT", root), patch("builtins.print"), patch.object(
                aa_poc.ArtificialAnalysisClient, "fetch_snapshot", new_callable=AsyncMock,
                side_effect=AAError("AA HTTP 401"),
            ) as fetch, patch.object(aa_poc, "load_mock_snapshot") as mock:
                status = await aa_poc.run(self.args(output=output))
            self.assertEqual(status, 1)
            fetch.assert_awaited_once_with(max_pages=10, refresh=True)
            mock.assert_not_called()
            self.assertEqual(output.read_text(), "previous real audit")
            self.assertIn("Live API verification failed", output.with_name("aa-data-audit-last-attempt.md").read_text())


if __name__ == "__main__":
    unittest.main()
