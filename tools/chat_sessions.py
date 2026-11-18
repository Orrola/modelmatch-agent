"""Bounded chat state and public projections, independent of analysis evidence sessions."""

import math
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit


class ChatAccessError(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def visible_text(text):
    """Remove known credentials before storing visible messages or projecting traces."""
    text = str(text)
    text = re.sub(r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|$)", "[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+\S+|AIza[\w-]+|\baa_[A-Za-z0-9]{16,}|\bsk-[A-Za-z0-9_-]{16,}", "[REDACTED]", text)
    text = re.sub(r'''(?i)(["']?(?:api_key|access_token|refresh_token|client_secret|password)["']?\s*[:=]\s*)["']?[^\s,"'}]+''', r"\1[REDACTED]", text)
    for key, value in os.environ.items():
        if len(value) >= 12 and any(part in key.upper() for part in ("API_KEY", "TOKEN", "PASSWORD", "CLIENT_SECRET")):
            text = text.replace(value, "[REDACTED]")
    return text


@dataclass
class ChatSession:
    session_id: str
    touched: float
    messages: list = field(default_factory=list)
    task_history: list = field(default_factory=list)
    requirements: str = ""
    confirmed_plan: dict | None = None
    pending_clarification: bool = False
    analysis_id: str | None = None
    pending_scope: str | None = None
    alpha_override: float | None = None
    weight_adjusted: bool = False
    busy: bool = False

    def append(self, role, content):
        text = visible_text(content)
        if len(text) > 6000:
            text = text[:5900] + "\n[Visible history excerpt truncated; confirmed requirements are retained separately.]"
        self.messages.append({"role": role, "content": text})
        self.messages[:] = self.messages[-10:]
        self.task_history.append({"role": role, "content": text})
        self.task_history[:] = self.task_history[-10:]


class ChatSessionStore:
    """Single-event-loop admission; no claim of durability or distributed ownership."""

    def __init__(self, *, ttl=1800, capacity=100, clock=time.monotonic):
        self.ttl, self.capacity, self.clock = ttl, capacity, clock
        self.sessions, self.expired = {}, {}
        self.evaluation_runs = 0

    def require_enabled(self):
        if os.getenv("MODELMATCH_CHAT_EVALUATION_ENABLED") != "1":
            raise ChatAccessError(403, "Chat evaluation is disabled by the server operator.")

    def check_allowance(self):
        try:
            limit = int(os.getenv("MODELMATCH_CHAT_EVALUATION_MAX_RUNS", "3"))
        except ValueError:
            raise ChatAccessError(503, "Chat evaluation allowance is not configured correctly.") from None
        if not 1 <= limit <= 100:
            raise ChatAccessError(503, "Chat evaluation allowance must be between 1 and 100 workflows per instance.")
        if self.evaluation_runs >= limit:
            raise ChatAccessError(429, "This instance's chat research allowance is exhausted. No new research was started.")

    def prune(self):
        now = self.clock()
        self.expired = {key: end for key, end in self.expired.items() if end > now}
        for key, session in list(self.sessions.items()):
            if not session.busy and now - session.touched >= self.ttl:
                del self.sessions[key]
                self.expired[key] = now + self.ttl
        while len(self.expired) > self.capacity:
            del self.expired[next(iter(self.expired))]

    def claim(self, session_id):
        self.prune()
        if session_id is None:
            if len(self.sessions) >= self.capacity:
                raise ChatAccessError(503, "Chat session capacity is reached. No new session was created.")
            session_id = secrets.token_urlsafe(32)
            self.sessions[session_id] = ChatSession(session_id, self.clock())
        session = self.sessions.get(session_id)
        if session is None:
            if session_id in self.expired:
                raise ChatAccessError(410, "This chat session expired. Start a new session with session_id=null.")
            raise ChatAccessError(404, "Chat session not found on this instance.")
        if session.busy:
            raise ChatAccessError(409, "Another turn is active in this chat session.")
        session.busy = True
        session.touched = self.clock()
        return session

    def release(self, session):
        session.busy = False
        session.touched = self.clock()


def task_turn(session, message):
    """Recognize explicit task boundaries; ambiguous topic changes request confirmation."""
    if not session.requirements:
        return "new"
    if re.search(r"\b(new|different|unrelated|independent)\s+(task|topic|project|use case)\b|\b(?:switch|start over)\b|\binstead\b", message, re.I):
        return "new"
    if re.search(r"\b(?:same|current|existing)\s+(?:task|assistant|project)\b", message, re.I):
        return "refine"
    declaration = re.search(r"\bI (?:am |want to |need to )?(?:building|developing|build|develop)\b", message, re.I)
    from tools.task_classification import DOMAINS
    old = {key for key, pattern in DOMAINS.items() if re.search(pattern, session.requirements, re.I)}
    current = {key for key, pattern in DOMAINS.items() if re.search(pattern, message, re.I)}
    purposes = {"coding": r"\bcoding\b|software development|generate code",
                "tool_agent": r"customer support|tool calling|external APIs",
                "shopping": r"shopping assistant|product recommendations|online retail"}
    old |= {key for key, pattern in purposes.items() if re.search(pattern, session.requirements, re.I)}
    current |= {key for key, pattern in purposes.items() if re.search(pattern, message, re.I)}
    if declaration:
        return "confirm_scope" if old and current and current <= old else "new"
    if old and current and not current <= old and not session.pending_clarification:
        return "confirm_scope"
    question = re.search(r"\b(why|explain|evidence|sources?|citations?|breakdown|context window|token limit)\b", message, re.I)
    question = question or re.match(r"(?:what|how|which|can|could|does|is|show|compare)\b", message, re.I)
    amendment = re.search(r"\b(change|modify|update|must|require|prefer|at least|at most)\b", message, re.I)
    amendment = amendment or re.search(r"\d", message) and re.search(r"budget|per month|ttft|latency|tokens", message, re.I)
    if question and not amendment:
        return "evidence"
    return "refine"


CHANGE_TERMS = {
    "monthly_cost_usd": r"\bbudget\b|\bmonthly (?:cost|spend)\b",
    "ttft": r"\bttft\b|time to first token|\blatency\b",
    "output_speed": r"output speed|tokens per second|\btokens/s\b",
    "context_window": r"context window|combined context",
    "max_input_tokens": r"input (?:context|token|limit)|input documents",
    "max_output_tokens": r"output (?:limit|token)",
    "deployment": r"\bdeployment\b|on-prem",
    "data_residency": r"\bresidency\b",
    "monthly_requests": r"requests? (?:per |a )?month|monthly requests",
    "avg_input_tokens": r"input tokens|tokens (?:per|for each) input",
    "avg_output_tokens": r"output tokens|tokens (?:per|for each) output",
    "user_alpha": r"\balpha\b|general (?:intelligence )?weight|use.case weight",
}


def changed_fields(message):
    return {key for key, pattern in CHANGE_TERMS.items() if re.search(pattern, message, re.I)}


def public_tool_calls(calls):
    """Project actual calls through a whitelist; never return free-form task/prompts."""
    allowed = {"model_ids", "model_id", "domain", "match_status", "role", "status", "snapshot_id",
               "model_count", "valid_model_count", "valid_evidence_count", "missing_model_count",
               "missing_manifest", "missing_fields", "field", "required", "evidence_ids", "evidence_id",
               "valid_evidence", "metric", "value", "unit", "statistic", "source_type", "source_url",
               "retrieved_at", "index_version", "evidence_status", "verification_status", "data_mode",
               "preview_limit", "complete_evidence_retained_server_side", "error", "truncated"}

    def project(value, depth=0):
        if depth > 7:
            return {"truncated": True}
        if isinstance(value, dict):
            output = {}
            for key, child in value.items():
                if key not in allowed:
                    continue
                if key == "error":
                    child = child if child in ("tool_failed", "researcher_run_failed") else "tool_execution_failed"
                if key == "source_url":
                    if not isinstance(child, str):
                        continue
                    try:
                        url = urlsplit(child)
                    except ValueError:
                        continue
                    if url.scheme != "https" or url.query or url.fragment or url.username or url.password:
                        continue
                output[key] = project(child, depth+1)
            return output
        if isinstance(value, list):
            items = [project(child, depth+1) for child in value[:12]]
            return items if len(value) <= 12 else {"items": items, "truncated": True, "omitted_count": len(value)-12}
        if isinstance(value, str):
            return visible_text(value)[:500]
        if value is None or isinstance(value, bool) or isinstance(value, (int, float)) and math.isfinite(value):
            return value
        return None

    result = []
    for call in calls:
        if call.get("status") in ("proposed", "not_executed"):
            continue
        identity = {key: visible_text(call.get(key, ""))[:128] for key in ("call_id", "agent", "context_id", "tool", "status")}
        identity.update({key: call.get(key) for key in ("started_at", "ended_at", "elapsed_seconds")})
        identity.update(arguments=project(call.get("arguments")) if isinstance(call.get("arguments"), dict) else {},
                        result=project(call.get("result")) if isinstance(call.get("result"), dict) else {"redacted": True})
        result.append(identity)
    return result
