"""Origin checks behind TLS ingress without provider calls or proxy-header trust."""

import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
import app as web
from tools.chat_sessions import ChatSessionStore

PUBLIC_HOST = "modelmatch-agent-git-978311583991.europe-west1.run.app"
PUBLIC_ORIGIN = f"https://{PUBLIC_HOST}"


class RequestOriginTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MODELMATCH_OFFLINE": "0", "MODELMATCH_PUBLIC_ORIGIN": PUBLIC_ORIGIN,
                                         "MODELMATCH_CHAT_EVALUATION_ENABLED": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.service = web.app.state.modelmatch
        self.service.saved.clear()
        self.service.recent.clear()
        self.service.active = 0
        self.service.chat_sessions = ChatSessionStore()
        result = {"status": "clarification_needed", "questions": ["Specify the task."], "markdown": "Specify the task."}
        self.run = AsyncMock(return_value=(result, None))
        self.stub = patch.object(self.service, "run", self.run)
        self.stub.start()
        self.addCleanup(self.stub.stop)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=web.app, client=("198.51.100.10", 1234)),
            base_url=f"http://{PUBLIC_HOST}")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def post(self, path="/chat", headers=None):
        body = {"message": "Analyze financial research."} if path == "/chat" else {"question": "Analyze financial research.", "approve_live": True}
        return await self.client.post(path, json=body, headers=headers or {})

    async def test_tls_ingress_mismatch_is_reproduced_without_public_origin(self):
        os.environ.pop("MODELMATCH_PUBLIC_ORIGIN")
        response = await self.post(headers={"Origin": PUBLIC_ORIGIN, "X-Forwarded-Proto": "https"})
        self.assertEqual(response.status_code, 403)
        self.run.assert_not_awaited()

    async def test_exact_public_origin_accepts_sse_over_internal_http(self):
        response = await self.post("/api/modelmatch/analyze", {"Origin": PUBLIC_ORIGIN, "X-Forwarded-Proto": "https"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[0]["type"], "start")
        self.assertEqual(events[-1]["type"], "done")
        self.run.assert_awaited_once()

    async def test_exact_public_origin_accepts_normal_post(self):
        response = await self.post(headers={"Origin": PUBLIC_ORIGIN})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"response", "session_id", "tool_calls"})
        self.run.assert_awaited_once()

    async def test_exact_public_origin_passes_recalculation_origin_gate(self):
        key = self.service.remember({"status": "clarification_needed"}, None)
        response = await self.client.post("/api/modelmatch/recalculate",
            headers={"Origin": PUBLIC_ORIGIN}, json={"analysis_id": key, "user_alpha": 0.7})
        self.assertEqual(response.status_code, 409)
        self.assertIn("no decision evidence", response.json()["detail"])
        self.run.assert_not_awaited()

    async def test_illegal_origins_are_rejected_for_sse_and_normal_post(self):
        for path in ("/chat", "/api/modelmatch/analyze", "/api/modelmatch/recalculate"):
            for origin in ("https://evil.example", f"http://{PUBLIC_HOST}", PUBLIC_ORIGIN + ".evil.example", "null"):
                response = await self.post(path, {"Origin": origin})
                self.assertEqual(response.status_code, 403, (path, origin))
        self.run.assert_not_awaited()

    async def test_forged_forwarded_headers_cannot_authorize_another_origin(self):
        response = await self.post(headers={"Origin": "https://evil.example", "Host": "evil.example",
            "X-Forwarded-Host": PUBLIC_HOST, "X-Forwarded-Proto": "https",
            "Forwarded": f"host={PUBLIC_HOST};proto=https"})
        self.assertEqual(response.status_code, 403)
        response = await self.post(headers={"Origin": PUBLIC_ORIGIN, "Host": "evil.example",
            "X-Forwarded-Host": PUBLIC_HOST, "X-Forwarded-Proto": "https"})
        self.assertEqual(response.status_code, 403)
        self.run.assert_not_awaited()

    async def test_forwarded_host_is_not_used_as_an_alternative_allowlist(self):
        response = await self.post(headers={"Origin": "https://evil.example",
            "X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "https"})
        self.assertEqual(response.status_code, 403)
        self.run.assert_not_awaited()

    async def test_local_http_and_https_remain_same_origin_without_configuration(self):
        os.environ.pop("MODELMATCH_PUBLIC_ORIGIN")
        for origin in ("http://127.0.0.1:8000", "http://localhost:8000", "https://localhost:8000"):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url=origin) as client:
                response = await client.post("/chat", headers={"Origin": origin},
                    json={"message": "Analyze financial research."})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.run.await_count, 3)

    async def test_spoofed_forwarded_proto_does_not_fix_local_origin_mismatch(self):
        os.environ.pop("MODELMATCH_PUBLIC_ORIGIN")
        response = await self.post(headers={"Origin": PUBLIC_ORIGIN,
            "X-Forwarded-Proto": "https", "X-Forwarded-Host": PUBLIC_HOST})
        self.assertEqual(response.status_code, 403)
        self.run.assert_not_awaited()

    async def test_invalid_operator_configuration_fails_closed(self):
        for value in ("*", "https://one.example,https://two.example", PUBLIC_ORIGIN + "/api", "https://user:password@example.com"):
            os.environ["MODELMATCH_PUBLIC_ORIGIN"] = value
            self.assertEqual((await self.post(headers={"Origin": PUBLIC_ORIGIN})).status_code, 503)
        self.run.assert_not_awaited()

    async def test_duplicate_and_malformed_origins_fail_closed(self):
        for headers in ([('Origin', PUBLIC_ORIGIN), ('Origin', 'https://evil.example')],
                        {"Origin": PUBLIC_ORIGIN + "/api"}, {"Origin": PUBLIC_ORIGIN + "#"},
                        {"Origin": PUBLIC_ORIGIN + ":invalid"}):
            self.assertEqual((await self.post(headers=headers)).status_code, 403)
        self.run.assert_not_awaited()

    async def test_missing_origin_preserves_non_browser_api_behavior(self):
        self.assertEqual((await self.post()).status_code, 200)
        self.run.assert_awaited_once()

    async def test_origin_fix_does_not_bypass_server_evaluation_gate(self):
        with patch.dict(os.environ, {"MODELMATCH_CHAT_EVALUATION_ENABLED": "0"}):
            response = await self.client.post("/chat", headers={"Origin": PUBLIC_ORIGIN},
                json={"message": "Analyze financial research."})
        self.assertEqual(response.status_code, 403)
        self.run.assert_not_awaited()

    async def test_installed_uvicorn_ignores_proxy_headers_from_untrusted_peer(self):
        observed = []
        async def capture(scope, receive, send):
            observed.append(scope["scheme"])
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})
        app = ProxyHeadersMiddleware(capture, trusted_hosts=["127.0.0.1"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("198.51.100.10", 1)),
                                     base_url="http://local") as client:
            await client.get("/", headers={"X-Forwarded-Proto": "https"})
        self.assertEqual(observed, ["http"])
