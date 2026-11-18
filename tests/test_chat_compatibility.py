"""Project 1 chat contracts using isolated HTTP apps and real offline SDK agents."""

import asyncio
import json
import os
import re
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
from modelmatch_web import ChatWebInput, install_modelmatch
from modelmatch_schemas import ParsedConstraint
from tests.fake_modelmatch import default_plan
from offline_model import OfflineModel
from tools.chat_sessions import ChatAccessError, ChatSessionStore, public_tool_calls

TASK = "Analyze financial documents for a finance team."


class HistoryModel(OfflineModel):
    """Simple explicit numeric extraction for synthetic history regression cases only."""

    payloads = []
    stale_budget = False

    async def get_response(self, system_instructions, input, *args, **kwargs):
        response = await super().get_response(system_instructions, input, *args, **kwargs)
        messages = input if isinstance(input, list) else [{"role": "user", "content": input}]
        payload = json.loads(next(m["content"] for m in reversed(messages) if m.get("role") == "user"))
        if payload.get("stage") == "parse":
            self.payloads.append(payload)
            plan = json.loads(response.output[0].content[0].text)
            raw = payload["user_input"]
            for pattern, metric in ((r"budget \$(\d+)", "monthly_cost_usd"), (r"ttft (\d+)", "ttft")):
                matches = list(re.finditer(pattern, raw, re.I))
                if matches:
                    match = matches[0] if self.stale_budget and metric == "monthly_cost_usd" else matches[-1]
                    plan["constraints"].append({"metric": metric, "target": float(match[1]),
                        "statistic": "mean" if metric == "ttft" else None, "source_quote": match[0]})
            for pattern, key in ((r"(\d+) requests per month", "monthly_requests"),
                                 (r"(\d+) input tokens", "avg_input_tokens"),
                                 (r"(\d+) output tokens", "avg_output_tokens")):
                matches = list(re.finditer(pattern, raw, re.I))
                if matches:
                    match = matches[-1]
                    plan["workload"][key] = {"value": float(match[1]), "source_quote": match[0]}
            response.output[0].content[0].text = json.dumps(plan)
        return response


class ChatStoreTests(unittest.TestCase):
    def test_unrelated_soft_preference_does_not_relax_confirmed_hard_requirement(self):
        for latest, expected_hard in (("Change ttft 1 with optional budget $200", True),
                                      ("Change ttft 1; ttft is soft", False)):
            session = ChatSessionStore().claim(None)
            previous = default_plan()
            previous.constraints = [ParsedConstraint(metric="ttft", target=2, hard=True,
                source_quote="ttft 2", hard_source_quote="must ttft 2")]
            session.confirmed_plan = previous.model_dump()
            request = ChatWebInput(question=TASK + " must ttft 2\n" + latest)
            request._session, request._latest = session, latest
            current = default_plan()
            current.constraints = [ParsedConstraint(metric="ttft", target=1, source_quote="ttft 1")]
            request.validate_history(current)
            self.assertEqual(current.constraints[0].hard, expected_hard)
            self.assertTrue(session.confirmed_plan["constraints"][0]["hard"])

    def test_unknown_expired_capacity_and_single_active_turn(self):
        now = [10.0]
        store = ChatSessionStore(capacity=1, ttl=30, clock=lambda: now[0])
        session = store.claim(None)
        with self.assertRaises(ChatAccessError) as error:
            store.claim(session.session_id)
        self.assertEqual(error.exception.status, 409)
        with self.assertRaises(ChatAccessError) as error:
            store.claim(None)
        self.assertEqual(error.exception.status, 503)
        store.release(session)
        now[0] += 31
        with self.assertRaises(ChatAccessError) as error:
            store.claim(session.session_id)
        self.assertEqual(error.exception.status, 410)
        with self.assertRaises(ChatAccessError) as error:
            store.claim("unknown-session")
        self.assertEqual(error.exception.status, 404)
        self.assertNotEqual(store.claim(None).session_id, session.session_id)

    def test_history_bound_does_not_discard_confirmed_requirements(self):
        store = ChatSessionStore()
        session = store.claim(None)
        session.requirements = "A confirmed user task."
        session.confirmed_plan = {"explicit_user_requirement": True}
        for i in range(20):
            session.append("user" if i % 2 else "assistant", str(i))
        self.assertEqual(len(session.messages), 10)
        self.assertEqual(len(session.task_history), 10)
        self.assertEqual(session.requirements, "A confirmed user task.")
        self.assertEqual(session.confirmed_plan, {"explicit_user_requirement": True})

    def test_public_projection_excludes_sensitive_free_form_and_unexecuted_calls(self):
        raw = {"call_id": "call-1", "agent": "Researcher B 2", "context_id": "context-1",
               "tool": "get_domain_evidence", "status": "completed", "arguments": {
                   "domain": "finance", "rationale": "PRIVATE_TASK", "api_key": "PRIVATE_KEY"},
               "result": {"system_prompt": "HIDDEN_PROMPT", "reasoning": "HIDDEN_REASONING",
                          "headers": {"Authorization": "PRIVATE_TOKEN"}, "model_count": 7,
                          "source_url": "https://example.com/?token=PRIVATE_TOKEN", "error": "RAW_PROVIDER_BODY"}}
        projected = public_tool_calls([raw, {**raw, "status": "proposed"}])
        self.assertEqual(len(projected), 1)
        self.assertEqual(projected[0]["agent"], "Researcher B 2")
        self.assertEqual(projected[0]["arguments"], {"domain": "finance"})
        self.assertEqual(projected[0]["result"], {"model_count": 7, "error": "tool_execution_failed"})
        for text in ("PRIVATE", "HIDDEN", "RAW_PROVIDER_BODY"):
            self.assertNotIn(text, json.dumps(projected))
        self.assertEqual(public_tool_calls([{**raw, "result": "RAW_PROVIDER_BODY"}])[0]["result"], {"redacted": True})


class ChatCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MODELMATCH_OFFLINE": "1", "MODELMATCH_PUBLIC_ORIGIN": "",
            "MODELMATCH_CHAT_EVALUATION_ENABLED": "1", "MODELMATCH_CHAT_EVALUATION_MAX_RUNS": "20"})
        self.env.start(); self.addCleanup(self.env.stop)
        self.app = FastAPI(); install_modelmatch(self.app)
        self.service = self.app.state.modelmatch
        self.store = self.service.chat_sessions
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://chat-test")
        self.guards = []
        for name in ("vertex_runtime.create_models", "google.genai.Client", "tools.artificial_analysis.ArtificialAnalysisClient.fetch_snapshot"):
            guard = self.enterContext(patch(name, side_effect=AssertionError("External provider calls are prohibited in chat tests.")))
            self.guards.append(guard)
            self.addCleanup(guard.assert_not_called)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def turn(self, message, session_id=None):
        response = await self.client.post("/chat", json={"message": message, "session_id": session_id})
        self.assertEqual(response.status_code, 200, response.text[:300])
        body = response.json()
        self.assertEqual(set(body), {"response", "session_id", "tool_calls"})
        return body

    async def test_exact_contract_nested_agents_and_independent_analysis_id(self):
        body = await self.turn(TASK)
        session = self.store.sessions[body["session_id"]]
        self.assertNotEqual(session.session_id, session.analysis_id)
        self.assertIn(session.analysis_id, self.service.saved)
        self.assertEqual(len(body["tool_calls"]), 6)
        self.assertEqual({c["agent"] for c in body["tool_calls"]}, {"Lead", "Researcher A 1", "Researcher B 2", "Researcher C 3"})
        self.assertNotIn("diagnostics", body)
        self.assertIn("synthetic", body["response"].lower())

    async def test_clarification_followup_uses_original_task_in_same_session(self):
        first = await self.turn("help")
        self.assertIn("Please clarify", first["response"])
        self.assertEqual(first["tool_calls"], [])
        self.assertTrue(self.store.sessions[first["session_id"]].pending_clarification)
        second = await self.turn(TASK, first["session_id"])
        self.assertEqual(second["session_id"], first["session_id"])
        self.assertTrue(second["tool_calls"])
        session = self.store.sessions[first["session_id"]]
        self.assertIn("help", session.requirements)
        self.assertIn(TASK, session.requirements)
        self.assertFalse(session.pending_clarification)
        self.assertEqual(len(session.messages), 4)

    async def test_monthly_workload_clarification_and_refinement_keep_verified_requirements(self):
        HistoryModel.payloads, HistoryModel.stale_budget = [], False
        with patch("offline_model.OfflineModel", HistoryModel):
            first = await self.turn(TASK + " budget $100; ttft 2")
            self.assertIn("Monthly cost", first["response"])
            second = await self.turn("1000 requests per month, 200 input tokens, 50 output tokens", first["session_id"])
            session = self.store.sessions[second["session_id"]]
            self.assertEqual(session.confirmed_plan["workload"]["monthly_requests"]["value"], 1000)
            third = await self.turn("Change the budget $200", second["session_id"])
            plan = session.confirmed_plan
            self.assertEqual({c["metric"]: c["target"] for c in plan["constraints"]}, {"monthly_cost_usd": 200, "ttft": 2})
            self.assertEqual(plan["workload"]["avg_output_tokens"]["value"], 50)
            self.assertEqual(third["session_id"], first["session_id"])
            self.assertIn("conversation_background", HistoryModel.payloads[-1])

    async def test_stale_changed_requirement_is_rejected_before_research(self):
        with patch("offline_model.OfflineModel", HistoryModel):
            first = await self.turn(TASK + " ttft 2")
            # A deliberately stale latest extraction must not retain the old target.
            original = HistoryModel.get_response
            async def stale(model, system_instructions, input, *args, **kwargs):
                response = await original(model, system_instructions, input, *args, **kwargs)
                if isinstance(input, list) and '"stage": "parse"' in input[-1].get("content", ""):
                    plan = json.loads(response.output[0].content[0].text)
                    plan["constraints"] = [{"metric": "ttft", "target": 2, "source_quote": "ttft 2", "statistic": "mean"}]
                    response.output[0].content[0].text = json.dumps(plan)
                return response
            with patch.object(HistoryModel, "get_response", stale):
                second = await self.turn("Change ttft 1", first["session_id"])
        self.assertIn("Please clarify", second["response"])
        self.assertEqual(second["tool_calls"], [])

    async def test_independent_task_clears_constraints_and_old_task_parse_background(self):
        HistoryModel.payloads = []
        with patch("offline_model.OfflineModel", HistoryModel):
            first = await self.turn(TASK + " ttft 2")
            second = await self.turn("I am building an AI coding assistant.", first["session_id"])
        session = self.store.sessions[second["session_id"]]
        self.assertNotIn("finance", session.requirements)
        self.assertEqual(session.confirmed_plan["constraints"], [])
        self.assertNotIn("finance", json.dumps(HistoryModel.payloads[-1]).lower())
        self.assertIn("finance", json.dumps(session.messages).lower())

    async def test_ambiguous_topic_switch_requires_scope_confirmation(self):
        first = await self.turn(TASK)
        second = await self.turn("Legal contract review", first["session_id"])
        self.assertIn("new independent task", second["response"])
        self.assertEqual(second["tool_calls"], [])
        third = await self.turn("yes", first["session_id"])
        session = self.store.sessions[third["session_id"]]
        self.assertEqual(session.requirements, "Legal contract review")
        self.assertNotIn("finance", session.requirements)

    async def test_saved_evidence_questions_and_alpha_adjustment_never_start_research(self):
        first = await self.turn(TASK)
        session = self.store.sessions[first["session_id"]]
        original = self.service.saved[session.analysis_id]["result"]
        old_alpha = original["decision"]["weights"]["alpha"]
        with patch.object(self.service, "run", side_effect=AssertionError("Saved evidence must not trigger research.")) as run:
            reply = await self.turn("Why was this model selected? Show evidence.", first["session_id"])
            self.assertIn("no new research", reply["response"])
            self.assertEqual(reply["tool_calls"], [])
            budget = await self.turn("What is my budget?", first["session_id"])
            self.assertEqual(budget["tool_calls"], [])
            self.assertIn("saved analysis", budget["response"])
            changed = await self.turn("Set alpha to 0.70", first["session_id"])
            self.assertIn("Writer explanation is stale", changed["response"])
            self.assertEqual(changed["tool_calls"], [])
            self.assertEqual(original["decision"]["weights"]["alpha"], old_alpha)
            self.assertEqual(session.confirmed_plan["user_alpha"]["value"], .7)
            run.assert_not_called()

    async def test_history_truncation_does_not_lose_task_and_evidence_expiry_never_refreshes(self):
        first = await self.turn(TASK)
        session = self.store.sessions[first["session_id"]]
        for _ in range(6):
            await self.turn("Show the evidence", first["session_id"])
        self.assertEqual(len(session.messages), 10)
        self.assertIn(TASK, session.requirements)
        self.service.saved.clear()
        with patch.object(self.service, "run", side_effect=AssertionError("No automatic refresh")) as run:
            result = await self.turn("Show the evidence", first["session_id"])
            self.assertIn("unavailable or expired", result["response"])
            run.assert_not_called()

    async def test_disabled_invalid_and_exhausted_allowance_fail_closed_across_sessions(self):
        with patch.dict(os.environ, {"MODELMATCH_CHAT_EVALUATION_ENABLED": "0"}):
            response = await self.client.post("/chat", json={"message": TASK})
            self.assertEqual(response.status_code, 403)
        for invalid in ("0", "-1", "bad", "101"):
            with patch.dict(os.environ, {"MODELMATCH_CHAT_EVALUATION_MAX_RUNS": invalid}):
                self.assertEqual((await self.client.post("/chat", json={"message": TASK})).status_code, 503)
        self.assertEqual(self.store.evaluation_runs, 0)
        with patch.dict(os.environ, {"MODELMATCH_CHAT_EVALUATION_MAX_RUNS": "2"}):
            first = await self.turn("help")
            second = await self.turn("help")
            self.assertNotEqual(first["session_id"], second["session_id"])
            with patch.object(self.service, "run", new_callable=AsyncMock) as run:
                self.assertEqual((await self.client.post("/chat", json={"message": TASK})).status_code, 429)
                self.assertEqual((await self.client.post("/chat", json={"message": TASK, "session_id": first["session_id"]})).status_code, 429)
                run.assert_not_awaited()
            self.assertEqual(self.store.evaluation_runs, 2)

    async def test_unknown_expired_and_invalid_request_shapes_never_start_research(self):
        with patch.object(self.service, "run", new_callable=AsyncMock) as run:
            self.assertEqual((await self.client.post("/chat", json={"message": TASK, "session_id": "x"*30})).status_code, 404)
            for body in ({"message": " "}, {"message": TASK, "approve_live": True},
                         {"question": TASK}, {"message": 42}, {"message": TASK, "session_id": ""}):
                self.assertEqual((await self.client.post("/chat", json=body)).status_code, 422)
            session = self.store.claim(None); self.store.release(session); session.touched = 0
            self.assertEqual((await self.client.post("/chat", json={"message": TASK, "session_id": session.session_id})).status_code, 410)
            run.assert_not_awaited()

    async def test_rejected_new_task_does_not_destroy_the_previous_accepted_analysis(self):
        with patch.dict(os.environ, {"MODELMATCH_CHAT_EVALUATION_MAX_RUNS": "1"}):
            first = await self.turn(TASK)
            session = self.store.sessions[first["session_id"]]
            original = session.analysis_id
            rejected = await self.client.post("/chat", json={"message": "New task: build a coding assistant.",
                "session_id": first["session_id"]})
            self.assertEqual(rejected.status_code, 429)
            self.assertEqual(session.analysis_id, original)
            self.assertEqual(session.requirements, TASK)
            reply = await self.turn("Show the evidence", first["session_id"])
            self.assertIn("saved analysis", reply["response"])
            self.assertEqual(reply["tool_calls"], [])

    async def test_concurrent_turn_rejected_and_cancel_releases_locks_without_refund(self):
        first = await self.turn("help")
        entered = asyncio.Event()
        async def waiting(*args):
            entered.set(); await asyncio.Event().wait()
        with patch.object(self.service, "run", side_effect=waiting):
            pending = asyncio.create_task(self.client.post("/chat", json={"message": TASK, "session_id": first["session_id"]}))
            await asyncio.wait_for(entered.wait(), 2)
            response = await self.client.post("/chat", json={"message": TASK, "session_id": first["session_id"]})
            self.assertEqual(response.status_code, 409)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
        self.assertFalse(self.store.sessions[first["session_id"]].busy)
        self.assertEqual(self.service.active, 0)
        self.assertEqual(self.store.evaluation_runs, 2)

    async def test_provider_error_returns_safe_contract_and_actual_partial_tools(self):
        async def failed(request, hooks):
            hooks.calls.append({"call_id": "actual-call", "agent": "Researcher A 1", "context_id": "context",
                "tool": "get_general_evidence", "status": "running", "arguments": {}, "result": None,
                "started_at": 1, "ended_at": None, "elapsed_seconds": None})
            raise RuntimeError("PRIVATE_PROVIDER_BODY")
        with patch.object(self.service, "run", side_effect=failed) as run:
            result = await self.turn(TASK)
        self.assertNotIn("PRIVATE_PROVIDER_BODY", json.dumps(result))
        self.assertIn("could not complete safely", result["response"])
        self.assertEqual(result["tool_calls"][0]["status"], "interrupted")
        self.assertEqual(self.service.active, 0)
        self.assertEqual(self.store.evaluation_runs, 1)
        run.assert_awaited_once()

    async def test_credentials_are_rejected_before_history_or_research(self):
        secret = "aa_" + "A"*32
        response = await self.client.post("/chat", json={"message": "Use key " + secret})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)
        self.assertNotIn(secret, json.dumps([s.messages for s in self.store.sessions.values()]))
        self.assertEqual(self.store.evaluation_runs, 0)

    async def test_assistant_history_cannot_authorize_a_new_constraint(self):
        first = await self.turn(TASK)
        session = self.store.sessions[first["session_id"]]
        session.append("assistant", "budget $999999")
        original = OfflineModel.get_response
        async def invented(model, system_instructions, input, *args, **kwargs):
            response = await original(model, system_instructions, input, *args, **kwargs)
            payload = json.loads(input[-1]["content"])
            if payload.get("stage") == "parse":
                plan = json.loads(response.output[0].content[0].text)
                plan["constraints"] = [{"metric": "monthly_cost_usd", "target": 999999, "source_quote": "budget $999999"}]
                response.output[0].content[0].text = json.dumps(plan)
            return response
        with patch.object(OfflineModel, "get_response", invented):
            result = await self.turn("Also summarize the reports", first["session_id"])
        self.assertIn("Please clarify", result["response"])
        self.assertEqual(result["tool_calls"], [])
        self.assertEqual(session.confirmed_plan["constraints"], [])

    async def test_repeated_same_domain_declaration_requires_scope_confirmation(self):
        first = await self.turn(TASK)
        result = await self.turn("I am building an AI financial assistant.", first["session_id"])
        self.assertIn("new independent task", result["response"])
        self.assertEqual(result["tool_calls"], [])

    async def test_default_gate_is_disabled_and_instance_default_allowance_is_three(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ChatAccessError) as error:
                self.store.require_enabled()
            self.assertEqual(error.exception.status, 403)
            self.store.evaluation_runs = 3
            with self.assertRaises(ChatAccessError) as error:
                self.store.check_allowance()
            self.assertEqual(error.exception.status, 429)
