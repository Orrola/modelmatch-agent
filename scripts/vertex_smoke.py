"""Opt-in ADC/Vertex tests. Diagnostics are offline; paid modes require approval."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Literal

from agents import Agent, RunConfig, Runner, function_tool
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from tools.artificial_analysis import utc_now
from vertex_runtime import CallBudget, VertexConfig, check_permissions, create_models, diagnose, safe_error

ROOT = Path(__file__).resolve().parents[1]


class StructuredProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    number: Literal[7]


def limited_snapshot(snapshot, limit=6):
    """Reuse actual AA data with explicit subset provenance, not synthetic scores."""
    from tools.model_evidence import RelevanceDecision, build_candidates
    if snapshot.get("data_mode") != "live":
        raise ValueError("Live pipeline acceptance requires a real AA snapshot, never a mock fixture.")
    prepared = build_candidates(snapshot, RelevanceDecision("Financial document analysis", "finance", "strong",
        "Candidate-selection assumption for a bounded integration test, not a validated task mapping."), shortlist_size=limit)
    ids = (prepared["shortlists"]["fully_evaluable"] + prepared["shortlists"]["provisional"])[:limit]
    wanted = set(ids)
    rows = [r for page in snapshot["pages"] for r in page["data"] if r["id"] in wanted]
    if not rows:
        raise ValueError("No real candidates are available for the bounded pipeline test.")
    page = {**snapshot["pages"][0], "data": rows,
            "pagination": {"page": 1, "has_more": len(rows) < prepared["counts_before_shortlist"]["total"] or not prepared["catalog_complete"]}}
    return {**snapshot, "pages": [page], "parent_snapshot_id": snapshot["snapshot_id"], "complete": not page["pagination"]["has_more"],
            "snapshot_id": hashlib.sha256((snapshot["snapshot_id"] + json.dumps(sorted(wanted))).encode()).hexdigest()[:16]}


async def run_test(args, diagnostics, config):
    report = {"mode": args.mode, "verification_mode": "actual_live_provider", "started_at": utc_now(),
              "configuration": asdict(config), "diagnostics": diagnostics,
              "cost": {"actual_cost_usd": None, "reason": "Billing and current provider prices were not queried; integration usage is separate from ModelMatch operational scoring."}}
    start = time.monotonic()
    cap = {"connectivity": 1, "structured": 1, "function": 2, "pipeline": 24, "grounding": 1}[args.mode]
    budget = CallBudget(max_calls=cap, capture_responses=args.mode in ("structured", "function", "pipeline"))
    report["limits"] = {"model_requests": cap, "max_output_tokens_per_request": config.max_output_tokens,
                        "max_prompt_chars": budget.max_prompt_chars, "provider_retries": 0,
                        "request_timeout_seconds": config.timeout_seconds, "pipeline_candidates": args.candidates,
                        "researcher_runs": 6, "followup_rounds": 1}
    if args.check_permissions:
        try:
            report["permission_checks"] = await asyncio.wait_for(asyncio.to_thread(check_permissions, config), timeout=45)
        except Exception as error:
            report["permission_checks"] = {"adc_refresh": "unverified_or_failed", "error": safe_error(error)}
        permissions = report["permission_checks"]
        if permissions.get("adc_refresh") != "success" or permissions.get("vertex_service", {}).get("state") == "DISABLED":
            report.update(status="blocked", reason="adc_or_service_configuration_requires_user_action")
            report.update(elapsed_seconds=round(time.monotonic() - start, 3), model_requests_attempted=0, model_usage=[])
            return report
        if permissions.get("iam", {}).get("status_code") == 200 and "aiplatform.endpoints.predict" not in permissions["iam"]["granted"]:
            report.update(status="blocked", reason="vertex_predict_permission_not_granted")
            report.update(elapsed_seconds=round(time.monotonic() - start, 3), model_requests_attempted=0, model_usage=[])
            return report
    try:
        if args.mode == "grounding":
            from tools.official_specs import OfficialSpecService, SpecRequest, VertexGroundingBackend
            snapshot = json.loads(args.snapshot.read_text())
            if snapshot.get("data_mode") != "live":
                raise ValueError("A real AA snapshot is required.")
            row = next(r for page in snapshot["pages"] for r in page["data"] if r["id"] == args.aa_model_id)
            request = SpecRequest(row["id"], row["name"], row["slug"], row["model_creator"]["name"], snapshot["snapshot_id"],
                                  ("context_window", "max_input_tokens", "max_output_tokens"))
            service = OfficialSpecService(VertexGroundingBackend(config, budget), allow_live=True, max_candidates=1, max_grounding_calls=1)
            result = await asyncio.wait_for(service.lookup(request), timeout=120)
            report.update(result=result, grounding_usage=service.telemetry,
                          status="verified" if any(r["verification_status"] == "verified" for r in result["records"].values()) else "unknown")
            report["limits"].update(grounding_requests=1, requested_search_queries=1,
                                    provider_internal_search_query_hard_cap_available=False)
        else:
            model, researcher = create_models(config, budget)
            settings = config.settings()
            if args.mode == "pipeline":
                from modelmatch_schemas import OrchestrationLimits
                from orchestration import ModelMatchWorkflow
                snapshot = limited_snapshot(json.loads(args.snapshot.read_text()), args.candidates)
                report["candidate_subset"] = {"snapshot_id": snapshot["snapshot_id"],
                    "parent_snapshot_id": snapshot["parent_snapshot_id"],
                    "model_ids": [row["id"] for row in snapshot["pages"][0]["data"]],
                    "retrieved_at": snapshot["retrieved_at"]}
                report["limits"]["overall_pipeline_timeout_seconds"] = 180
                async def loader():
                    return snapshot
                workflow = ModelMatchWorkflow(model, researcher, settings=settings, snapshot_loader=loader,
                    limits=OrchestrationLimits(timeout_seconds=180, evidence_preview_size=6, shortlist_size=6))
                remaining = 180 - (time.monotonic() - start)
                if remaining <= 0:
                    raise TimeoutError("Pipeline setup exhausted the overall deadline.")
                try:
                    result = await asyncio.wait_for(workflow.run("Analyze financial documents for a finance team."), timeout=remaining)
                finally:
                    report["observed_plan"] = workflow.plan.model_dump() if workflow.plan is not None else None
                    report["execution_trace"] = workflow.trace
                    report["evidence_reviews"] = workflow.reviews
                    report["researcher_runs"] = workflow.researcher_count
                report.update(result=result, status="success" if result["status"] in ("supported", "provisional", "not_supported") and "decision" in result else "failed")
                report["pipeline_assertions"] = {
                    "same_turn_parallel_dispatch": False,
                    "targeted_followup_observed": any(e.get("round_number") == 1 for e in result["trace"] if e["type"] == "researcher_start"),
                    "writer_validation_passed": not result.get("writer_fallback", True),
                    "real_aa_candidates": len(snapshot["pages"][0]["data"])}
                starts = [e for e in result["trace"] if e["type"] == "researcher_start" and e["round_number"] == 0]
                first_ids = {e["context_id"] for e in starts}
                report["pipeline_assertions"]["same_turn_parallel_dispatch"] = bool(
                    len(starts) == 3 and {e["role"] for e in starts} == {"A", "B", "C"}
                    and any(b["stage"] == "dispatch" and len(b["calls"]) == 3
                            and set(b["calls"]) == {"research_a", "research_b", "research_c"} for b in workflow.batches))
                ends = [e for e in result["trace"] if e["type"] == "researcher_end" and e["context_id"] in first_ids]
                report["pipeline_assertions"]["independent_contexts"] = len(first_ids) == 3
                report["pipeline_assertions"]["parallel_execution_overlap"] = bool(len(starts) == 3 and len(ends) == 3 and max(e["monotonic"] for e in starts) < min(e["monotonic"] for e in ends))
                lead_contexts = {e["context_id"] for e in result["trace"] if e["type"] == "llm_started" and e["agent"] == "Lead"}
                report["pipeline_assertions"]["same_lead_context"] = len(lead_contexts) == 1 and bool(result["reviews"])
                report["pipeline_assertions"]["grounding_executed"] = bool(result.get("official_specifications"))
                required = ("same_turn_parallel_dispatch", "writer_validation_passed", "independent_contexts", "parallel_execution_overlap", "same_lead_context")
                if not all(report["pipeline_assertions"][key] for key in required) or report["pipeline_assertions"]["grounding_executed"]:
                    report["status"] = "failed"
            elif args.mode == "function":
                invocations = []
                @function_tool(failure_error_function=None)
                def echo_marker(marker: str) -> str:
                    """Return the marker unchanged to prove a real function invocation."""
                    if invocations or marker != "modelmatch-smoke":
                        raise ValueError("Unexpected or duplicate smoke-test function invocation.")
                    invocations.append(marker)
                    return marker
                agent = Agent(name="Function smoke", model=model, model_settings=settings, tools=[echo_marker])
                result = await Runner.run(agent, "Call echo_marker exactly once with marker modelmatch-smoke, then reply exactly DONE.",
                                          max_turns=2, run_config=RunConfig(tracing_disabled=True))
                report.update(status="success" if invocations == ["modelmatch-smoke"] and str(result.final_output).strip() == "DONE" else "failed",
                              function_invocations=len(invocations), final_output=str(result.final_output),
                              tool_results=[{"name": "echo_marker", "arguments": {"marker": marker}, "result": marker} for marker in invocations])
            elif args.mode == "structured":
                agent = Agent(name="Structured smoke", model=model, model_settings=settings, output_type=StructuredProbe)
                result = await Runner.run(agent, 'Return status "ok" and number 7, using the required schema.', max_turns=1, run_config=RunConfig(tracing_disabled=True))
                report.update(status="success" if isinstance(result.final_output, StructuredProbe) else "failed",
                              final_output=result.final_output.model_dump() if isinstance(result.final_output, StructuredProbe) else str(result.final_output))
            else:
                agent = Agent(name="Connectivity probe", model=model, model_settings=settings)
                result = await Runner.run(agent, "Reply exactly OK. No tools or explanation.", max_turns=1, run_config=RunConfig(tracing_disabled=True))
                report.update(status="success" if str(result.final_output).strip() == "OK" else "reachable_but_unexpected_output")
    except Exception as error:
        report.update(status="failed", error=safe_error(error))
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - start, 3)
        report["model_usage"] = budget.records
        report["model_requests_attempted"] = budget.calls
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("diagnostic", "connectivity", "compatibility", "structured", "function", "pipeline", "grounding"), default="diagnostic")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approve-billable", action="store_true", help="Explicit approval for paid tests beyond the initial probe.")
    parser.add_argument("--check-permissions", action="store_true", help="Read-only OAuth/IAM/service checks before the probe.")
    parser.add_argument("--snapshot", type=Path, default=ROOT / ".cache/aa/aa-free-snapshot.json")
    parser.add_argument("--aa-model-id")
    parser.add_argument("--candidates", type=int, default=6)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.mode != "diagnostic" and not args.live:
        parser.error("Provider calls require --live; no request was made.")
    if args.mode not in ("diagnostic", "connectivity") and not args.approve_billable:
        parser.error("This paid test requires --approve-billable after user approval.")
    if not 1 <= args.candidates <= 6:
        parser.error("Pipeline candidate limit must be between 1 and 6.")
    if args.mode == "grounding" and not args.aa_model_id:
        parser.error("Grounding requires an exact --aa-model-id from the real snapshot.")
    load_dotenv(ROOT / ".env", override=False)
    diagnostics = diagnose()
    output = args.output or ROOT / ".cache/vertex" / f"{args.mode}.json"
    try:
        config = VertexConfig.from_environment(diagnostics=diagnostics)
        if args.mode == "diagnostic":
            report = {"mode": "diagnostic", "verification_mode": "local_metadata_only", "diagnostics": diagnostics, "configuration": asdict(config)}
        elif args.mode == "compatibility":
            async def compatibility():
                results = []
                for mode in ("structured", "function"):
                    child = argparse.Namespace(**{**vars(args), "mode": mode})
                    record = await run_test(child, diagnostics, replace(config, max_output_tokens=512))
                    results.append(record)
                    if record["status"] != "success":
                        break
                return {"mode": "compatibility", "verification_mode": "actual_live_provider", "results": results,
                        "status": "success" if len(results) == 2 and all(r["status"] == "success" for r in results) else "failed",
                        "limits": {"model_requests": 3, "max_output_tokens_per_request": 512, "provider_retries": 0}}
            report = asyncio.run(compatibility())
        else:
            tokens = 128 if args.mode == "connectivity" else 512 if args.mode in ("structured", "function") else 1024 if args.mode == "grounding" else 2048
            report = asyncio.run(run_test(args, diagnostics, replace(config, max_output_tokens=tokens)))
    except Exception as error:
        report = {"mode": args.mode, "status": "blocked", "error": safe_error(error), "diagnostics": diagnostics}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    # Never dump provider responses or authentication objects to the terminal.
    print(json.dumps({"mode": args.mode, "status": report.get("status", "local_configuration_checked"),
                      "report": str(output), "error": report.get("error")}, indent=2))
    return 0 if report.get("status") in (None, "success", "verified", "reachable_but_unexpected_output") else 1


if __name__ == "__main__":
    raise SystemExit(main())
