"""Bounded web/API adapter over the approved ModelMatch research and decision engine."""

from __future__ import annotations

import asyncio
import json
import math
import os
import secrets
import time
import uuid
from collections import deque
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from context_panel import AgentContexts, PanelHooks, _plain
from modelmatch_schemas import OrchestrationLimits, ParsedConstraint, StatedNumber
from orchestration import ModelMatchWorkflow
from tools.decision import decide
from tools.official_specs import public_diagnostics
from tools.run_diagnostics import failure_details, log_metadata

ROOT = Path(__file__).parent
CONTRACT = "provisional-modelmatch-chat-v1"


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


class ChatInput(WebInput):
    question: str = Field(default="", max_length=6000)
    message: str = Field(min_length=3, max_length=6000)

    @field_validator("message")
    @classmethod
    def meaningful_message(cls, value):
        return WebInput.meaningful(value)


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
        output = await super().lead(stage, payload)
        if stage == "parse":
            output = self.web_input.apply(output)
        return output


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


class AnalysisService:
    """Single-worker MVP with bounded ephemeral evidence storage; no disk session dependency."""

    def __init__(self):
        self.saved = {}
        self.active = 0
        self.recent = deque()
        self.ttl = 1800
        self.capacity = 8
        self.max_saved_bytes = 64 * 1024 * 1024

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

    def remember(self, result, prepared):
        self.prune()
        size = len(json.dumps([result, prepared], default=str).encode())
        if size > self.max_saved_bytes // 2:
            return None
        while self.saved and (len(self.saved) >= self.capacity or sum(v["size"] for v in self.saved.values()) + size > self.max_saved_bytes):
            del self.saved[next(iter(self.saved))]
        key = secrets.token_urlsafe(32)
        self.saved[key] = {"expires": time.monotonic() + self.ttl, "result": deepcopy(result), "prepared": prepared, "size": size}
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
        return result, workflow.prepared() if "decision" in result else None


def install_modelmatch(app):
    router = APIRouter()
    service = AnalysisService()
    app.state.modelmatch = service

    @router.get("/modelmatch")
    def page():
        return FileResponse(ROOT / "static/modelmatch.html", headers={"Cache-Control": "no-cache"})

    @router.get("/modelmatch.js")
    def javascript():
        return FileResponse(ROOT / "static/modelmatch.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/modelmatch.css")
    def stylesheet():
        return FileResponse(ROOT / "static/modelmatch.css", media_type="text/css")

    @router.get("/healthz")
    def health():
        return {"status": "ok", "service": "modelmatch", "provider_checked": False}

    @router.get("/api/modelmatch/config")
    def config():
        return {"mode": "offline_synthetic" if service.offline else "live_vertex", "chat_contract": CONTRACT,
                "contract_verified": False, "session_ttl_seconds": service.ttl, "grounding_enabled": False}

    async def execute(body, emit, run_id=None):
        hooks = WebHooks(emit, run_id)
        try:
            result, prepared = await asyncio.wait_for(service.run(body, hooks), timeout=190)
            result.setdefault("run_id", hooks.run_id)
            hooks.finish(result.get("status") not in ("error", "insufficient_evidence"))
            result["tool_calls"] = hooks.calls
            key = service.remember(result, prepared)
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
        return {"analysis_id": body.analysis_id, "decision": decision, "research_rerun": False,
                "run_id": original.get("run_id"),
                "writer_alpha": original_alpha, "writer_explanation_stale": original_alpha != decision["weights"]["alpha"]}

    @router.post("/chat")
    async def chat(body: ChatInput):
        values = body.model_dump(exclude={"message", "question"})
        request = WebInput(question=body.message, **values)
        service.acquire(request.approve_live)
        run_id = str(uuid.uuid4())
        try:
            response = await execute(request, lambda event: None, run_id)
        except Exception:
            raise HTTPException(503, "Analysis could not complete safely.", headers={"X-ModelMatch-Run-ID": run_id}) from None
        finally:
            service.active -= 1
        return {"contract": CONTRACT, "contract_verified": False, "reply": response["result"]["markdown"],
                "tool_calls": response["result"]["tool_calls"], **response}

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
