"""Bounded web/API adapter over the approved ModelMatch research and decision engine."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import secrets
import time
import uuid
from collections import deque
from copy import deepcopy
from decimal import Decimal
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from context_panel import AgentContexts, PanelHooks, _plain
from modelmatch_schemas import OrchestrationLimits, ParsedConstraint, ParsedPlan, StatedNumber, WriterOutput
from orchestration import ModelMatchWorkflow, PlanValidationError
from tools.chat_sessions import (ChatAccessError, ChatSessionStore, changed_fields, public_tool_calls,
                                 task_turn, visible_text, CHANGE_TERMS)
from tools.decision import decide
from tools.official_specs import public_diagnostics
from tools.run_diagnostics import failure_details, log_metadata

ROOT = Path(__file__).parent
CONTRACT = "project1-chat-v1"


def normalized_origin(value: str) -> str:
    """Parse a single HTTP origin without credentials, paths or header lists."""
    if not value.isascii() or any(char.isspace() for char in value) or "?" in value or "#" in value:
        raise ValueError("Invalid origin.")
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or "," in parsed.netloc or "\\" in parsed.netloc):
        raise ValueError("Invalid origin.")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port is not None and port != {"http": 80, "https": 443}[parsed.scheme]:
        host += f":{port}"
    return f"{parsed.scheme}://{host}"


def request_origin_allowed(request: Request, public_origin: str | None) -> bool:
    """Use an operator-set public origin, never client-supplied forwarded headers."""
    expected = normalized_origin(public_origin) if public_origin else None
    origins = request.headers.getlist("origin")
    hosts = request.headers.getlist("host")
    if len(hosts) != 1 or len(origins) > 1:
        return False
    try:
        if expected:
            # TLS can end at the ingress; require the original Host to match too.
            if normalized_origin(f"{urlsplit(expected).scheme}://{hosts[0]}") != expected:
                return False
        else:
            expected = normalized_origin(str(request.base_url))
        return not origins or normalized_origin(origins[0]) == expected
    except ValueError:
        return False


class WebInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    question: str = Field(min_length=3, max_length=6000)
    monthly_budget: float | None = Field(default=None, ge=0, le=1e12)
    monthly_requests: float | None = Field(default=None, ge=0, le=1e12)
    avg_input_tokens: float | None = Field(default=None, ge=0, le=1e9)
    avg_output_tokens: float | None = Field(default=None, ge=0, le=1e9)
    ttft: float | None = Field(default=None, ge=0, le=1e6)
    output_speed: float | None = Field(default=None, ge=0, le=1e9)
    context_window: float | None = Field(default=None, gt=0, le=1e9)
    hard_constraints: list[str] = Field(default_factory=list, max_length=4)
    user_alpha: float | None = Field(default=None, ge=0, le=1)
    approve_live: bool = False

    @field_validator("question")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("A task description is required.")
        return value.strip()

    @field_validator("hard_constraints")
    @classmethod
    def allowed_hard(cls, value):
        if any(k not in {"monthly_budget", "ttft", "output_speed", "context_window"} for k in value):
            raise ValueError("Unsupported hard constraint field.")
        return list(dict.fromkeys(value))

    @field_validator("monthly_budget", "monthly_requests", "avg_input_tokens", "avg_output_tokens", "ttft", "output_speed", "context_window", "user_alpha", mode="before")
    @classmethod
    def real_numbers(cls, value):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))):
            raise ValueError("Numeric fields must contain JSON numbers.")
        return value

    @model_validator(mode="after")
    def hard_targets_present(self):
        if any(getattr(self, key) is None for key in self.hard_constraints):
            raise ValueError("Each hard constraint requires an explicit target.")
        return self

    def quoted_fields(self):
        labels = {"monthly_budget": "Monthly budget USD", "monthly_requests": "Monthly requests",
            "avg_input_tokens": "Average input tokens", "avg_output_tokens": "Average output tokens",
            "ttft": "Mean TTFT target seconds", "output_speed": "Mean output speed minimum tokens per second",
            "context_window": "Combined context window minimum tokens", "user_alpha": "General Intelligence weight alpha"}
        return {key: ("Mandatory requirement: " if key in self.hard_constraints else "") + f"{label}: {format(Decimal(str(getattr(self, key))), 'f')}"
                for key, label in labels.items() if getattr(self, key) is not None}

    def prompt(self):
        fields = self.quoted_fields()
        return self.question + ("\n\nStructured requirements (explicit user inputs; authoritative for these fields):\n"
                                + "\n".join(fields.values()) if fields else "")

    def apply(self, plan):
        """Bind explicitly supplied form fields; never infer unspecified requirements."""
        plan = plan.model_copy(deep=True)
        quotes = self.quoted_fields()
        metric_map = {"monthly_budget": "monthly_cost_usd", "ttft": "ttft", "output_speed": "output_speed", "context_window": "context_window"}
        for field, metric in metric_map.items():
            if field not in quotes:
                continue
            hard = field in self.hard_constraints
            plan.constraints = [c for c in plan.constraints if c.metric != metric]
            plan.constraints.append(ParsedConstraint(metric=metric, target=getattr(self, field), hard=hard,
                statistic="mean" if metric in ("ttft", "output_speed") else None,
                source_quote=quotes[field], hard_source_quote=quotes[field] if hard else None))
        for field in ("monthly_requests", "avg_input_tokens", "avg_output_tokens"):
            if field in quotes:
                setattr(plan.workload, field, StatedNumber(value=getattr(self, field), source_quote=quotes[field]))
        if "user_alpha" in quotes:
            plan.user_alpha = StatedNumber(value=self.user_alpha, source_quote=quotes["user_alpha"])
        return plan


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=6000)
    session_id: str | None = Field(default=None, min_length=20, max_length=128)

    @field_validator("message")
    @classmethod
    def meaningful_message(cls, value):
        value = WebInput.meaningful(value)
        if visible_text(value) != value:
            raise ValueError("Remove credentials from the message before submitting it.")
        return value


class ChatOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: str
    session_id: str
    tool_calls: list[dict]


class ChatWebInput(WebInput):
    """Internal adapter state; public analyze requests never accept these attributes."""

    _session: object = PrivateAttr(default=None)
    _latest: str = PrivateAttr(default="")

    def validate_history(self, plan):
        prior = self._session.confirmed_plan
        if prior is None:
            return
        previous = ParsedPlan.model_validate(prior)
        changes = changed_fields(self._latest)
        # An anchored latest extraction also identifies an amendment without keywords.
        for constraint in plan.constraints:
            if constraint.source_quote and constraint.source_quote.casefold() in self._latest.casefold():
                changes.add(constraint.metric)
        for old in previous.constraints:
            if old.metric not in changes:
                plan.constraints = [c for c in plan.constraints if c.metric != old.metric] + [old]
            else:
                removal = re.search(r"\b(?:remove|drop|ignore)\s+(?:the\s+)?(?:" + CHANGE_TERMS.get(old.metric, r"(?!)") + ")", self._latest, re.I)
                current = next((c for c in plan.constraints if c.metric == old.metric), None)
                if removal:
                    plan.constraints = [c for c in plan.constraints if c.metric != old.metric]
                elif current is None or current.source_quote.casefold() not in self._latest.casefold():
                    raise PlanValidationError("chat_update_unresolved", "Please restate the changed requirement and its target explicitly.")
                elif old.hard:
                    metric = CHANGE_TERMS.get(old.metric, r"(?!)")
                    soft = re.search(r"(?:\b(?:soft|optional|prefer)\s+(?:" + metric + r")|(?:" + metric
                        + r")\s+(?:is\s+)?(?:soft|optional|a preference)\b)", self._latest, re.I)
                    if not soft:
                        current.hard, current.hard_source_quote = True, old.hard_source_quote
        for key in ("monthly_requests", "avg_input_tokens", "avg_output_tokens"):
            old, current = getattr(previous.workload, key), getattr(plan.workload, key)
            if old is not None and key not in changes:
                setattr(plan.workload, key, old)
            elif old is not None and (current is None or current.source_quote.casefold() not in self._latest.casefold()):
                raise PlanValidationError("chat_workload_update_unresolved", "Please state the changed workload value explicitly.")
        if previous.user_alpha is not None and "user_alpha" not in changes:
            plan.user_alpha = previous.user_alpha
        elif previous.user_alpha is not None and (plan.user_alpha is None or plan.user_alpha.source_quote.casefold() not in self._latest.casefold()):
            raise PlanValidationError("chat_weight_update_unresolved", "Please state the new alpha explicitly.")


class RecalculateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    analysis_id: str = Field(min_length=20, max_length=128)
    user_alpha: float | None = Field(default=None, ge=0, le=1)

    @field_validator("user_alpha", mode="before")
    @classmethod
    def real_alpha(cls, value):
        return WebInput.real_numbers(value)


class WebWorkflow(ModelMatchWorkflow):
    """The Lead still parses/classifies; explicit form inputs are bound by Python."""

    def __init__(self, *args, web_input, **kwargs):
        super().__init__(*args, **kwargs)
        self.web_input = web_input

    async def lead(self, stage, payload):
        if stage == "parse" and isinstance(self.web_input, ChatWebInput):
            payload = {**payload, "conversation_background": [
                    {"role": message["role"], "content": message["content"][:500]}
                    for message in self.web_input._session.task_history],
                "conversation_rule": "Visible assistant history is background only, never a source for requirements. "
                    "Extract only from user_input for the current task. The latest explicit user amendment takes precedence. "
                    "Do not quote old assistant text as a user requirement."}
        output = await super().lead(stage, payload)
        if stage == "parse":
            output = self.web_input.apply(output)
        return output

    def validate_requirements(self, plan, user_input):
        if isinstance(self.web_input, ChatWebInput):
            self.web_input.validate_history(plan)
        return super().validate_requirements(plan, user_input)


def bounded(value, limit=16000):
    value = public_diagnostics(value)
    text = json.dumps(value, default=str)
    return value if len(text) <= limit else {"truncated": True, "preview": text[:limit]}


class WebHooks(PanelHooks):
    """Keep nested call identities and actual hook execution intervals."""

    def __init__(self, emit, run_id=None):
        self.run_id = run_id or str(uuid.uuid4())
        def correlated(event):
            emit({**event, "run_id": self.run_id})
        super().__init__(AgentContexts(), correlated)
        self.calls = []

    def activity(self, agent, text):
        super().activity(agent, text)

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        await super().on_llm_start(context, agent, system_prompt, input_items)
        self.emit({"type": "stage", "agent": agent.name, "stage": context.context.stage, "status": "running"})

    async def on_llm_end(self, context, agent, response):
        await super().on_llm_end(context, agent, response)
        for item in response.output:
            row = _plain(item)
            if row.get("type") != "function_call":
                continue
            try:
                args = json.loads(row.get("arguments", "{}"))
            except ValueError:
                args = {"unparsed": row.get("arguments")}
            call = {"call_id": row.get("call_id"), "agent": agent.name, "run_id": self.run_id,
                    "context_id": context.context.context_id, "tool": row.get("name"),
                    "arguments": bounded(args), "status": "proposed", "result": None,
                    "started_at": None, "ended_at": None, "elapsed_seconds": None}
            self.calls.append(call)
            self.emit({"type": "tool_trace", "call": deepcopy(call)})

    async def on_tool_start(self, context, agent, tool):
        await super().on_tool_start(context, agent, tool)
        call = next((c for c in self.calls if c["agent"] == agent.name and c["tool"] == tool.name and c["status"] == "proposed"), None)
        if call:
            call.update(status="running", started_at=time.time())
            self.emit({"type": "tool_trace", "call": deepcopy(call)})

    async def on_controller_tool_start(self, context, agent, tool):
        """Attribute actual controller-dispatched tools without inventing model calls."""
        self.calls.append({"call_id": context.tool_call_id, "agent": agent.name, "run_id": self.run_id,
            "context_id": context.context.context_id, "tool": tool.name,
            "arguments": bounded(json.loads(context.tool_arguments)), "status": "proposed",
            "origin": "controller", "result": None, "started_at": None,
            "ended_at": None, "elapsed_seconds": None})
        self.emit({"type": "tool_trace", "call": deepcopy(self.calls[-1])})

    async def on_tool_end(self, context, agent, tool, result):
        call = next((c for c in self.calls if c["agent"] == agent.name and c["tool"] == tool.name and c["status"] == "running"), None)
        if call:
            try:
                parsed = json.loads(result) if isinstance(result, str) else result
            except ValueError:
                parsed = result
            call.update(status="failed" if isinstance(parsed, dict) and parsed.get("error") else "completed",
                        result=bounded(parsed), ended_at=time.time())
            call["elapsed_seconds"] = round(call["ended_at"] - call["started_at"], 6)
            self.emit({"type": "tool_trace", "call": deepcopy(call)})

    async def on_agent_end(self, context, agent, output):
        self.activity(agent.name, "Generation completed; controller validation is pending.")

    def finish(self, success):
        for call in self.calls:
            if call["status"] in ("proposed", "running"):
                call.update(status="not_executed" if call["status"] == "proposed" else "interrupted", ended_at=time.time())
                self.emit({"type": "tool_trace", "call": deepcopy(call)})


@dataclass
class AnalysisRun:
    """Private persistence context with backward-compatible two-value unpacking."""
    result: dict
    prepared: dict | None
    selection_context: dict | None

    def __iter__(self):
        return iter((self.result, self.prepared))


class AnalysisService:
    """Single-worker MVP with bounded ephemeral evidence storage; no disk session dependency."""

    def __init__(self):
        self.saved = {}
        self.active = 0
        self.recent = deque()
        self.ttl = 1800
        self.capacity = 8
        self.max_saved_bytes = 64 * 1024 * 1024
        self.chat_sessions = ChatSessionStore()

    @property
    def offline(self):
        return os.getenv("MODELMATCH_OFFLINE") == "1"

    def acquire(self, approved):
        if not self.offline and not approved:
            raise HTTPException(403, "Live analysis requires explicit approval and may incur provider charges.")
        now = time.monotonic()
        while self.recent and self.recent[0] < now - 60:
            self.recent.popleft()
        if self.active >= 2 or len(self.recent) >= 6:
            raise HTTPException(429, "Analysis capacity reached. Try again later.")
        self.active += 1
        self.recent.append(now)

    def prune(self):
        now = time.monotonic()
        self.saved = {k: v for k, v in self.saved.items() if v["expires"] > now}

    def remember(self, result, prepared, selection_context=None):
        self.prune()
        size = len(json.dumps([result, prepared, selection_context], default=str).encode())
        if size > self.max_saved_bytes // 2:
            return None
        while self.saved and (len(self.saved) >= self.capacity or sum(v["size"] for v in self.saved.values()) + size > self.max_saved_bytes):
            del self.saved[next(iter(self.saved))]
        key = secrets.token_urlsafe(32)
        self.saved[key] = {"expires": time.monotonic() + self.ttl, "result": deepcopy(result),
                           "prepared": deepcopy(prepared), "selection_context": deepcopy(selection_context), "size": size}
        return key

    async def run(self, request, hooks):
        from tools.artificial_analysis import AAError, ArtificialAnalysisClient, load_mock_snapshot
        if self.offline:
            from offline_model import OfflineModel
            model = researcher = OfflineModel()
            settings = None
            budget = None
            async def loader():
                return load_mock_snapshot(ROOT / "examples/offline-aa.json")
        else:
            from vertex_runtime import CallBudget, VertexConfig, create_models
            config = await asyncio.to_thread(VertexConfig.from_environment, root=ROOT)
            log_metadata("provider_configuration", run_id=hooks.run_id, project=config.project, location=config.location,
                         lead_writer_model=config.model, researcher_model=config.researcher_model,
                         max_output_tokens=config.max_output_tokens, timeout_seconds=config.timeout_seconds, num_retries=0)
            budget = CallBudget(max_calls=24)
            model, researcher = create_models(config, budget)
            settings = config.settings()
            async def loader():
                snapshot = await ArtificialAnalysisClient(cache_dir=Path(os.getenv("MODELMATCH_CACHE_DIR", "/tmp/modelmatch-aa"))).fetch_snapshot()
                if snapshot.get("data_mode") != "live":
                    raise AAError("Live mode requires an actual AA snapshot; synthetic replacement is not allowed.")
                return snapshot
        workflow = WebWorkflow(model, researcher, settings=settings, hooks=hooks, web_input=request,
            snapshot_loader=loader, limits=OrchestrationLimits(timeout_seconds=180, shortlist_size=6, evidence_preview_size=6))
        result = await workflow.run(request.prompt())
        if workflow.plan is not None:
            result["plan"] = workflow.plan.model_dump()
        result["execution_mode"] = "offline_synthetic" if self.offline else "live_vertex"
        result["integration_usage"] = {"model_requests": budget.calls if budget else 0,
            "records": budget.records if budget else [], "actual_cost_usd": None}
        return AnalysisRun(result, workflow.prepared() if "decision" in result else None, getattr(workflow, "selection_context", None))


def install_modelmatch(app):
    router = APIRouter()
    service = AnalysisService()
    app.state.modelmatch = service

    @app.exception_handler(RequestValidationError)
    async def chat_validation_error(request, error):
        if request.url.path == "/chat":
            return JSONResponse(status_code=422, content={"detail": [
                {"loc": [part if isinstance(part, int) or part in ("body", "message", "session_id") else "unexpected_field"
                         for part in entry["loc"]], "type": entry["type"], "msg": "Invalid chat request."}
                for entry in error.errors()]})
        return await request_validation_exception_handler(request, error)

    @router.get("/modelmatch")
    def page():
        return FileResponse(ROOT / "static/modelmatch.html", headers={"Cache-Control": "no-cache"})

    @router.get("/modelmatch.js")
    def javascript():
        return FileResponse(ROOT / "static/modelmatch.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/recommendation-views.js")
    def recommendation_javascript():
        return FileResponse(ROOT / "static/recommendation_views.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/modelmatch.css")
    def stylesheet():
        return FileResponse(ROOT / "static/modelmatch.css", media_type="text/css")

    @router.get("/healthz")
    def health():
        return {"status": "ok", "service": "modelmatch", "provider_checked": False}

    @router.get("/api/modelmatch/config")
    def config():
        return {"mode": "offline_synthetic" if service.offline else "live_vertex", "chat_contract": CONTRACT,
                "contract_verified": True, "session_ttl_seconds": service.ttl, "grounding_enabled": False}

    async def execute(body, emit, run_id=None, *, hooks=None):
        hooks = hooks or WebHooks(emit, run_id)
        try:
            outcome = await asyncio.wait_for(service.run(body, hooks), timeout=190)
            result, prepared = outcome
            result.setdefault("run_id", hooks.run_id)
            hooks.finish(result.get("status") not in ("error", "insufficient_evidence"))
            result["tool_calls"] = hooks.calls
            key = service.remember(result, prepared, getattr(outcome, "selection_context", None))
            return {"analysis_id": key, "result": result, "run_id": hooks.run_id}
        except asyncio.CancelledError:
            log_metadata("request_cancelled", run_id=hooks.run_id)
            raise
        except Exception as error:
            log_metadata("request_failed", run_id=hooks.run_id, error=failure_details(error))
            raise
        finally:
            hooks.finish(False)

    @router.post("/api/modelmatch/analyze")
    async def analyze(body: WebInput):
        service.acquire(body.approve_live)
        run_id = str(uuid.uuid4())
        queue = asyncio.Queue(maxsize=512)
        overflow = False
        def emit(event):
            nonlocal overflow
            if overflow:
                return
            try:
                queue.put_nowait(public_diagnostics({**event, "run_id": run_id}))
            except asyncio.QueueFull:
                overflow = True
                task.cancel()
        async def work():
            try:
                result = await execute(body, emit, run_id)
                emit({"type": "done", **result})
            except asyncio.CancelledError:
                raise
            except Exception as error:
                emit({"type": "error", "error": failure_details(error), "message": "Analysis could not start or complete. Check the existing Vertex project, ADC credentials, and AA API configuration. No synthetic results were substituted."})
        task = asyncio.create_task(work())
        task.add_done_callback(lambda _: setattr(service, "active", service.active - 1))
        async def events():
            try:
                yield "data: " + json.dumps({"type": "start", "run_id": run_id}) + "\n\n"
                while True:
                    if overflow:
                        yield "data: " + json.dumps({"type": "error", "run_id": run_id, "message": "Event capacity exceeded. Analysis stopped."}) + "\n\n"
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), 10)
                    except asyncio.TimeoutError:
                        yield ': heartbeat\n\n'
                        continue
                    yield "data: " + json.dumps(event, default=str, allow_nan=False) + "\n\n"
                    if event["type"] in ("done", "error"):
                        break
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        return StreamingResponse(events(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-ModelMatch-Run-ID": run_id})

    @router.post("/api/modelmatch/recalculate")
    async def recalculate(body: RecalculateInput):
        service.prune()
        saved = service.saved.get(body.analysis_id)
        if saved is None:
            raise HTTPException(404, "Analysis expired or is unavailable on this worker. Run a new analysis.")
        if saved["prepared"] is None:
            raise HTTPException(409, "This analysis has no decision evidence to recalculate.")
        original = saved["result"]
        decision = decide(saved["prepared"], task_type=original["decision"]["weights"]["task_type"], user_alpha=body.user_alpha)
        original_alpha = original["decision"]["weights"]["alpha"]
        from tools.selection_pipeline import selection_for_decision
        selection_fields, _ = selection_for_decision(decision, saved["prepared"], frozen_context=saved.get("selection_context"))
        original_selection = original.get("selection")
        current_selection = selection_fields["selection"]
        writer_selection_id = original_selection["selection_id"] if original_selection else None
        current_selection_id = current_selection["selection_id"] if current_selection else None
        return {"analysis_id": body.analysis_id, "decision": decision, "research_rerun": False,
                "run_id": original.get("run_id"),
                **selection_fields, "writer_alpha": original_alpha, "writer_selection_id": writer_selection_id,
                "writer_narrative_available": original.get("writer_status") == "accepted",
                "writer_explanation_stale": original_alpha != decision["weights"]["alpha"]
                    or writer_selection_id != current_selection_id or selection_fields["selector"]["status"] == "unavailable"}

    def frozen_chat_response(session, alpha=None):
        service.prune()
        saved = service.saved.get(session.analysis_id)
        if saved is None or saved["prepared"] is None:
            return "The saved evidence is unavailable or expired. No new research was started. Please restate the task if you want a new analysis."
        result = saved["result"]
        current_selection = result.get("selection")
        if alpha is not None or session.weight_adjusted:
            from recommendation import render_recommendation, writer_payload
            from tools.selection_pipeline import selection_for_decision
            selected_alpha = alpha if alpha is not None else session.alpha_override
            decision = decide(saved["prepared"], task_type=result["decision"]["weights"]["task_type"], user_alpha=selected_alpha)
            fields, _ = selection_for_decision(decision, saved["prepared"], frozen_context=saved.get("selection_context"))
            current_selection = fields["selection"]
            payload = writer_payload(decision, fields["selection"])
            intent = WriterOutput(candidate_ids=payload["candidate_ids"], evidence_ids=payload["evidence_ids"], validation_steps=["task_pilot"])
            text = "Deterministic weight adjustment using frozen evidence. The original Writer explanation is stale; no new Writer or research call was made.\n\n" + render_recommendation(decision, intent, fields["selection"])
        else:
            decision = result["decision"]
            text = "Using the saved analysis; no new research was performed.\n\n"
            if result.get("writer_fallback"):
                text += "The original Writer failed; this is its labeled deterministic fallback.\n\n"
            text += result["markdown"]
        text += "\n\nSupporting evidence (observed values only):\n"
        ids = {eid for slot in (current_selection or {}).get("slots", {}).values()
               if slot.get("candidate") for eid in slot["candidate"]["evidence_ids"]}
        for eid in sorted(ids):
            evidence = decision["evidence"][eid]
            if evidence["evidence_status"] == "observed":
                text += f"- {evidence['metric']}: {evidence['value']} {evidence.get('statistic') or ''}; source: {evidence['source_url']}\n"
        return text + "\nOfficial context, input/output limits and deployment specifications remain unknown unless explicitly verified in the saved evidence."

    @router.post("/chat", response_model=ChatOutput)
    async def chat(body: ChatInput):
        store = service.chat_sessions
        session = None
        chat_hooks = None
        acquired = False
        run_id = str(uuid.uuid4())
        try:
            store.require_enabled()
            session = store.claim(body.session_id)
            message = body.message
            mode = task_turn(session, message)
            if session.pending_scope:
                if re.fullmatch(r"yes[.!]?|new task[.!]?", message, re.I):
                    mode, message = "new", session.pending_scope
                elif re.fullmatch(r"no[.!]?|same task[.!]?", message, re.I):
                    mode, message = "refine", session.pending_scope
                session.pending_scope = None
            session.append("user", body.message)

            def answer(text, calls=()):
                text = visible_text(text)
                session.append("assistant", text)
                return ChatOutput(response=text, session_id=session.session_id, tool_calls=public_tool_calls(calls))

            if mode == "confirm_scope":
                session.pending_scope = message
                return answer("Is this a new independent task? Reply 'yes' to start it without the previous task's constraints, or 'no' to refine the current task.")
            alpha_match = re.fullmatch(r"(?:set |change |use )?alpha\s*(?:to|=|:)?\s*(0(?:\.\d+)?|1(?:\.0+)?)[.!]?", message, re.I)
            if alpha_match and session.analysis_id:
                if len(session.requirements) + len(message) + 31 > 6000:
                    raise ChatAccessError(413, "Confirmed task context is full. Start a new session rather than silently discarding requirements.")
                text = frozen_chat_response(session, float(alpha_match[1]))
                if "original Writer explanation is stale" in text:
                    session.alpha_override, session.weight_adjusted = float(alpha_match[1]), True
                    session.requirements += "\nAdditional task information: " + message
                    if session.confirmed_plan:
                        session.confirmed_plan["user_alpha"] = {"value": session.alpha_override, "source_quote": message}
                return answer(text)
            if mode == "evidence":
                return answer(frozen_chat_response(session))
            requirements = message if mode == "new" else session.requirements + "\nAdditional task information: " + message
            if len(requirements) > 6000:
                raise ChatAccessError(413, "Confirmed task context exceeds 6,000 characters. Start a new session; requirements were not truncated.")
            def retain_requirements():
                if mode == "new":
                    session.confirmed_plan, session.analysis_id = None, None
                    session.pending_clarification = False
                    session.alpha_override, session.weight_adjusted = None, False
                    session.pending_scope = None
                    session.task_history = [{"role": "user", "content": message}]
                session.requirements = requirements

            if len(requirements) < 3:
                retain_requirements()
                session.pending_clarification = True
                return answer("Please describe the task you want the model to perform.")
            store.check_allowance()
            service.acquire(True)
            acquired = True
            store.evaluation_runs += 1
            retain_requirements()
            request = ChatWebInput(question=requirements, approve_live=True)
            request._session, request._latest = session, message
            session.analysis_id = None
            chat_hooks = WebHooks(lambda event: None, run_id)
            response = await execute(request, lambda event: None, run_id, hooks=chat_hooks)
            result = response["result"]
            session.pending_clarification = result.get("status") == "clarification_needed"
            if result.get("plan") and result.get("status") not in ("clarification_needed", "error"):
                session.confirmed_plan = deepcopy(result["plan"])
            if result.get("decision"):
                session.analysis_id = response["analysis_id"]
                session.alpha_override, session.weight_adjusted = None, False
            else:
                session.analysis_id = None
            text = result["markdown"]
            if result.get("writer_fallback"):
                text = "Writer generation failed. This is a deterministic fallback, not an accepted Writer response.\n\n" + text
            return answer(text, result.get("tool_calls", ()))
        except ChatAccessError as error:
            raise HTTPException(error.status, str(error)) from None
        except HTTPException:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log_metadata("chat_turn_failed", run_id=run_id, error=failure_details(error))
            text = "Analysis could not complete safely. No synthetic results were substituted. The failed turn was not automatically retried."
            if session:
                session.append("assistant", text)
                return ChatOutput(response=text, session_id=session.session_id, tool_calls=public_tool_calls(chat_hooks.calls if chat_hooks else ()))
            raise HTTPException(503, text) from None
        finally:
            if acquired:
                service.active -= 1
            if session:
                store.release(session)

    @app.middleware("http")
    async def modelmatch_request_limits(request: Request, call_next):
        if request.method == "POST" and (request.url.path.startswith("/api/modelmatch/") or request.url.path == "/chat"):
            from fastapi.responses import JSONResponse
            try:
                allowed = request_origin_allowed(request, os.getenv("MODELMATCH_PUBLIC_ORIGIN") or None)
            except ValueError:
                return JSONResponse({"detail": "Public origin configuration is invalid."}, status_code=503)
            if not allowed:
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            payload = bytearray()
            async for chunk in request.stream():
                payload.extend(chunk)
                if len(payload) > 16000:
                    return JSONResponse({"detail": "Request body exceeds the size limit."}, status_code=413)
            def finite_float(raw):
                number = float(raw)
                if not math.isfinite(number):
                    raise ValueError("Non-finite number.")
                return number
            def reject_constant(raw):
                raise ValueError("Non-finite JSON constant.")
            try:
                json.loads(payload, parse_float=finite_float, parse_constant=reject_constant)
            except (ValueError, RecursionError):
                return JSONResponse({"detail": "Request body must be valid JSON with finite numbers."}, status_code=422)
            request._body = bytes(payload)
        return await call_next(request)

    app.include_router(router)
    return router
