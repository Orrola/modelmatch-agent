"""Preflight or explicitly authorized parse-only LOW experiment; never run research."""

import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from modelmatch_web import WebHooks, WebInput, WebWorkflow
from modelmatch_schemas import OrchestrationLimits
from orchestration import validate_plan
from tools.decision import TASK_DEFAULTS
from tools.run_diagnostics import failure_details
from tools.task_classification import resolve_task_type
from vertex_runtime import CallBudget, VertexConfig, create_models

ROOT = Path(__file__).resolve().parents[1]
CASE_IDS = {"financial", "coding", "customer_support", "ecommerce"}
LIMITS = {"max_model_requests": 4, "max_calls_per_case": 1, "max_output_tokens": 2048,
          "model_timeout_seconds": 30, "experiment_timeout_seconds": 140, "retries": 0,
          "aa_requests": 0, "grounding_requests": 0}


class ParseContractError(ValueError):
    validation_code = "eight_field_presence_not_verified"
    diagnostic_category = "schema_validation_error"


def prompt_hash(body):
    return hashlib.sha256(body.prompt().encode()).hexdigest()


def load_cases(path):
    try:
        rows = json.loads(path.read_text())["cases"]
        if len(rows) != 4 or {row["case_id"] for row in rows} != CASE_IDS:
            raise ValueError()
        for row in rows:
            body = WebInput.model_validate(row["request"])
            digest = prompt_hash(body)
            if not row.get("provenance") or digest != row["expected_input_hash"]:
                raise ValueError()
            baseline = row.get("baseline")
            if baseline and (baseline.get("input_hash") != digest or baseline.get("model") != "gemini-3.5-flash"
                             or baseline.get("max_output_tokens") != 2048 or baseline.get("timeout_seconds") != 30):
                raise ValueError()
        return rows
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("Four provenance-labeled original requests and matching input hashes are required; verify baseline settings too.") from None


def extraction_checks(plan, expectations):
    """Use explicit independent checks; never equate schema validity with correctness."""
    observed = {"task_type": plan.task_type,
                "constraint_metrics": [c.metric for c in plan.constraints]}
    if not expectations:
        return {"status": "manual_review_required", "checks": {}, "observed": observed}
    checks = {}
    terms = expectations.get("industry_terms")
    if terms:
        checks["industry"] = bool(plan.industry and any(term.casefold() in plan.industry.casefold() for term in terms))
    task_type = expectations.get("task_type")
    if task_type:
        checks["task_type"] = plan.task_type == task_type
    for key, value in expectations.get("workload", {}).items():
        stated = getattr(plan.workload, key)
        checks["workload." + key] = (stated.value if stated else None) == value
    expected_constraints = expectations.get("constraints")
    if expected_constraints is not None:
        actual = {c.metric: c for c in plan.constraints}
        checks["constraint_metrics"] = len(actual) == len(plan.constraints) and set(actual) == set(expected_constraints)
        for metric, fields in expected_constraints.items():
            for key, value in fields.items():
                checks[f"constraints.{metric}.{key}"] = metric in actual and getattr(actual[metric], key) == value
    status = "failed" if not all(checks.values()) else "passed" if task_type and terms and "workload" in expectations and expected_constraints is not None else "manual_review_required"
    return {"status": status, "checks": checks, "observed": observed}


def baseline_comparison(row, record):
    baseline = row.get("baseline")
    if not baseline:
        return {"status": "unavailable", "reason": "No historical baseline was supplied."}
    result = {"status": "same_input_historical_comparison", "baseline_run_id": baseline.get("run_id"),
              "baseline_thinking": baseline.get("thinking"), "deltas": {},
              "schema_comparison_scope": "historical_sdk_acceptance_only",
              "candidate_sdk_schema_accepted": record.get("sdk_schema_accepted")}
    for key in ("latency_seconds", "output_tokens", "reasoning_tokens"):
        before, after = baseline.get(key), record.get(key)
        result["deltas"][key] = after - before if isinstance(before, (int, float)) and isinstance(after, (int, float)) else None
    result["baseline_schema_accepted"] = baseline.get("schema_accepted")
    return result


async def run_case(row, config, model_factory=None):
    body = WebInput.model_validate(row["request"])
    budget = CallBudget(max_calls=1)
    model, researcher = (model_factory or create_models)(config, budget)
    hooks = WebHooks(lambda event: None)
    workflow = WebWorkflow(model, researcher, settings=config.settings(), hooks=hooks, web_input=body,
                          limits=OrchestrationLimits(max_agent_turns=1))
    record = {"case_id": row["case_id"], "run_id": workflow.run_id, "input_hash": prompt_hash(body),
              "schema_accepted": False, "sdk_schema_accepted": False, "business_validation_passed": False,
              "extraction_correctness": {"status": "not_evaluated"}}
    started = time.monotonic()
    try:
        plan = await workflow.lead("parse", {"user_input": body.prompt(), "task_weight_policy": TASK_DEFAULTS})
        record["sdk_schema_accepted"] = True
        observed = budget.records[-1].get("output_diagnostics", {}) if budget.records else {}
        record["schema_accepted"] = observed.get("validation_category") == "valid" and observed.get("missing_contract_fields") == []
        if not record["schema_accepted"]:
            raise ParseContractError("The raw response did not verify the complete eight-field contract.")
        proposed = plan.task_type
        plan.task_type, _ = resolve_task_type(body.prompt(), proposed)
        validate_plan(plan, body.prompt())
        record["business_validation_passed"] = True
        record["proposed_task_type"] = proposed
        record["extraction_correctness"] = extraction_checks(plan, row.get("expectations"))
        workflow.diagnostics.stage("parse", "accepted")
    except asyncio.CancelledError:
        raise
    except Exception as error:
        record["error"] = failure_details(error)
        workflow.diagnostics.stage("parse", "failed", error=record["error"])
    finally:
        workflow._closed = True
        record["parse_elapsed_seconds"] = round(time.monotonic() - started, 6)
        record["model_requests"] = budget.calls
        record["model_records"] = budget.records
        record["diagnostics"] = workflow.diagnostics.snapshot()
    call = budget.records[0] if budget.records else {}
    usage = call.get("usage") or {}
    record.update(latency_seconds=call.get("elapsed_seconds"), finish_reason=call.get("finish_reason"),
                  input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                  reasoning_tokens=call.get("reasoning_tokens"))
    record["comparison"] = baseline_comparison(row, record)
    return record


async def run_cases(rows, config):
    if not 1 <= len(rows) <= 4 or len({r["case_id"] for r in rows}) != len(rows):
        raise ValueError("At most four distinct planned cases are permitted.")
    if config.model != "gemini-3.5-flash" or config.max_output_tokens != 2048 or config.timeout_seconds != 30:
        raise ValueError("The approved model, output and timeout settings must remain unchanged.")
    results = []
    stopping_reason = "completed_planned_cases"
    for row in rows:
        record = await run_case(row, config)
        results.append(record)
        if not record["schema_accepted"] or not record["business_validation_passed"] or record["extraction_correctness"]["status"] == "failed":
            stopping_reason = "first_failed_case"
            break
    return {"mode": "live_parse_only_low", "results": results, "model_requests": sum(r["model_requests"] for r in results),
            "stopping_reason": stopping_reason,
            "not_run_cases": [row["case_id"] for row in rows[len(results):]],
            "semantic_review_pending": any(r["extraction_correctness"]["status"] == "manual_review_required" for r in results)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approve-billable", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.live and not args.approve_billable:
        parser.error("Live calls require separate --approve-billable authorization.")
    if args.output and not args.output.resolve().is_relative_to((ROOT / ".cache").resolve()):
        parser.error("Experiment artifacts must remain inside the ignored project .cache directory.")
    try:
        rows = load_cases(args.manifest)
    except ValueError as error:
        parser.error(str(error))
    if args.live:
        try:
            config = VertexConfig.from_environment(root=ROOT)
            report = asyncio.run(asyncio.wait_for(run_cases(rows, config), timeout=140))
        except Exception as error:
            report = {"mode": "live_parse_only_low", "stopping_reason": "experiment_boundary_error",
                      "error": failure_details(error), "model_requests": None, "results": [],
                      "note": "Consult correlated metadata logs for partial calls; no retry was made."}
    else:
        report = {"mode": "offline_preflight_no_model_calls", "model_requests": 0,
                  "cases": [{"case_id": r["case_id"], "input_hash": r["expected_input_hash"],
                             "baseline_available": bool(r.get("baseline"))} for r in rows]}
    report["limits"] = LIMITS
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if not args.live or (report.get("stopping_reason") == "completed_planned_cases" and not report.get("semantic_review_pending")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
