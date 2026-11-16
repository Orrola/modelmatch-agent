"""Metadata-only run diagnostics; never log prompts, outputs or hidden reasoning."""

import json
import asyncio
import logging
import os
import time
import uuid
import httpx
from contextvars import ContextVar
from datetime import datetime, timezone

CALL_CONTEXT = ContextVar("modelmatch_call_context", default={})
OUTPUT_DIAGNOSTICS = ContextVar("modelmatch_output_diagnostics", default=None)
logger = logging.getLogger("modelmatch.reliability")
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)
logger.propagate = False


def now():
    return datetime.now(timezone.utc).isoformat()


class ModelRequestTimeout(TimeoutError):
    """A per-model deadline, distinct from the controller's total deadline."""


def exception_chain(error):
    chain, seen = [], set()
    while error is not None and id(error) not in seen and len(chain) < 16:
        seen.add(id(error))
        chain.append(error)
        error = error.__cause__
    return chain


def is_timeout(error):
    return isinstance(error, (TimeoutError, httpx.TimeoutException)) or type(error).__name__ in ("APITimeoutError", "DeadlineExceeded")


def failure_details(error):
    """Classify exceptions without their messages, values or provider bodies."""
    from agents import ModelBehaviorError
    from pydantic import ValidationError

    chain = exception_chain(error)
    # Cancellation created internally by wait_for must not erase its TimeoutError.
    # An outward CancelledError, however, remains genuine cooperative cancellation.
    principal = next((item for item in chain if not isinstance(item, ModelRequestTimeout)
                      and (is_timeout(item) or isinstance(getattr(item, "status_code", None), int))), chain[-1])
    cause = error if isinstance(error, asyncio.CancelledError) else principal
    name = type(cause).__name__
    status = getattr(cause, "status_code", None)
    category = "execution_error"
    if isinstance(cause, asyncio.CancelledError):
        category = "cancelled"
    elif is_timeout(cause):
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
    result["cause_chain"] = [{"exception_type": type(item).__name__,
                               "status_code": getattr(item, "status_code", None) if isinstance(getattr(item, "status_code", None), int) else None}
                              for item in chain]
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
    if category == "schema_validation_error":
        output = next((getattr(item, "modelmatch_output_diagnostics", None) for item in chain
                       if getattr(item, "modelmatch_output_diagnostics", None)), None)
        if output:
            result["output_diagnostics"] = output
            result["category"] = output["failure_category"] or category
    return result


def inspect_lead_output(response, finish_reason):
    """Inspect syntax and the unchanged ParsedPlan contract without retaining text."""
    from pydantic import ValidationError
    from modelmatch_schemas import ParsedPlan

    parts = [part for item in getattr(response, "output", []) if getattr(item, "type", None) == "message"
             for part in getattr(item, "content", [])]
    text = "".join(part.text for part in parts if getattr(part, "type", None) == "output_text")
    limited = finish_reason in ("length", "MAX_TOKENS", "max_tokens")
    result = {"finish_reason": finish_reason, "response_characters": len(text),
              "markdown_fence_present": text.lstrip().startswith("```"),
              "refusal_present": any(getattr(part, "type", None) == "refusal" for part in parts),
              "generation_status": "incomplete_generation" if limited else "unknown" if finish_reason is None else "finished",
              "validation_category": None, "failure_category": None}
    try:
        parsed_json = json.loads(text)
    except (ValueError, RecursionError) as error:
        result["validation_category"] = "malformed_json"
        if isinstance(error, json.JSONDecodeError):
            result.update(json_line=error.lineno, json_column=error.colno, json_offset=error.pos)
    else:
        result["missing_contract_fields"] = [name for name in ParsedPlan.model_fields if name not in parsed_json] if isinstance(parsed_json, dict) else []
        try:
            ParsedPlan.model_validate_json(text, strict=True)
        except ValidationError as error:
            result["validation_category"] = "schema_validation_error"
            result["schema_errors"] = failure_details(error).get("schema_errors", [])
        else:
            result["validation_category"] = "valid"
    if result["validation_category"] != "valid":
        result["failure_category"] = "incomplete_generation" if limited else "provider_error" if result["refusal_present"] else result["validation_category"]
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
