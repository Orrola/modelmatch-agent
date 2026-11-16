"""Metadata-only run diagnostics; never log prompts, outputs or hidden reasoning."""

import json
import logging
import os
import time
import uuid
import httpx
from contextvars import ContextVar
from datetime import datetime, timezone

CALL_CONTEXT = ContextVar("modelmatch_call_context", default={})
logger = logging.getLogger("modelmatch.reliability")
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)
logger.propagate = False


def now():
    return datetime.now(timezone.utc).isoformat()


def failure_details(error):
    """Classify exceptions without their messages, values or provider bodies."""
    from agents import ModelBehaviorError
    from pydantic import ValidationError

    cause = error
    while getattr(cause, "__cause__", None) is not None:
        cause = cause.__cause__
    name = type(cause).__name__
    status = getattr(cause, "status_code", None)
    category = "execution_error"
    if isinstance(cause, (TimeoutError, httpx.TimeoutException)) or name in ("APITimeoutError", "DeadlineExceeded"):
        category = "timeout"
    elif isinstance(cause, (ValidationError, ModelBehaviorError, json.JSONDecodeError)):
        category = "schema_validation_error"
    elif getattr(cause, "validation_code", None):
        category = getattr(cause, "diagnostic_category", "evidence_validation_error")
    elif name == "BudgetExceeded":
        category = "budget_exceeded"
    elif isinstance(status, int) or any(x in name for x in ("APIError", "ConnectionError", "RateLimit", "ServiceUnavailable")):
        category = "provider_error"
    result = {"category": category, "exception_type": name,
            "status_code": status if isinstance(status, int) else None,
            "validation_code": getattr(cause, "validation_code", None),
            "rule": getattr(error, "rule", None)}
    if isinstance(cause, ValidationError):
        known = {"industry", "task_description", "task_quote", "task_type", "user_alpha", "constraints", "workload",
                 "clarification_questions", "metric", "target", "hard", "statistic", "source_quote", "hard_source_quote",
                 "monthly_requests", "avg_input_tokens", "avg_output_tokens", "value", "summary", "followups",
                 "stopping_reason", "role", "task", "reason", "model_ids", "completed", "observations",
                 "candidate_ids", "evidence_ids", "validation_steps"}
        result["schema_errors"] = [{"type": e["type"], "path": [p if isinstance(p, int) or p in known else "[field]" for p in e["loc"]]}
                                   for e in cause.errors(include_input=False, include_context=False, include_url=False)[:8]]
    if isinstance(cause, json.JSONDecodeError):
        result.update(json_line=cause.lineno, json_column=cause.colno)
    return result


class AccessQueryFilter(logging.Filter):
    """Compatibility GET inputs must not enter Uvicorn access-log query strings."""

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5 and isinstance(record.args[2], str):
            values = list(record.args)
            values[2] = values[2].split("?", 1)[0]
            record.args = tuple(values)
        return True


def log_metadata(event, **fields):
    # All callers pass only controlled metadata, never arbitrary exception text.
    logger.info(json.dumps({"event": event, "timestamp": now(), "revision": os.getenv("K_REVISION"), **fields}, allow_nan=False, default=str))


class RunDiagnostics:
    def __init__(self, run_id=None, emit=None):
        self.run_id = run_id or str(uuid.uuid4())
        self.emit = emit
        self.states = {}
        self.events = []
        self.started = {}

    def stage(self, stage, status, agent="Lead", **details):
        if status == "running":
            self.started[stage] = time.monotonic()
        row = {"run_id": self.run_id, "stage": stage, "agent": agent, "status": status,
               "timestamp": now(), **details}
        previous = self.states.get(stage, {})
        row["started_at"] = row["timestamp"] if status == "running" else previous.get("started_at")
        row["completed_at"] = row["timestamp"] if status == "completed" else None if status == "running" else previous.get("completed_at")
        row["accepted_at"] = row["timestamp"] if status == "accepted" else None
        if stage in self.started:
            row["elapsed_seconds"] = round(time.monotonic() - self.started[stage], 6)
        self.events.append(row)
        self.states[stage] = row
        log_metadata("stage_transition", **row)
        if self.emit:
            legacy = {"accepted": "completed", "completed": "running", "fallback": "failed", "not_reached": "skipped"}.get(status, status)
            self.emit({"type": "stage", **row, "status": legacy, "phase_status": status,
                       "controller_accepted": status == "accepted"})

    def finish(self, cancelled=False):
        for stage, row in list(self.states.items()):
            if row["status"] in ("running", "completed"):
                self.stage(stage, "cancelled", row["agent"])
        for stage in ("parse", "dispatch", "A", "B", "C", "review", "decision", "writer"):
            if stage not in self.states:
                self.stage(stage, "not_reached", "Writer" if stage == "writer" else "Decision Tool" if stage == "decision" else f"Researcher {stage}" if stage in "ABC" else "Lead")
        for stage in ("followup", "review_final"):
            if stage not in self.states:
                self.stage(stage, "not_reached")

    def snapshot(self):
        return {"run_id": self.run_id, "revision": os.getenv("K_REVISION"),
                "stages": dict(self.states), "events": list(self.events),
                "first_failure": next((e for e in self.events if e["status"] == "failed"), None)}


def response_metadata(response):
    """Retain explicit transport metadata only; absent fields remain null."""
    def field(name):
        value = getattr(response, name, None)
        return value if isinstance(value, (str, int, float, bool)) or value is None else None
    return {name: field(name) for name in ("finish_reason", "response_id", "request_id", "model_version")}
