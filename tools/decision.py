"""Deterministic ModelMatch decision engine over Phase 2A evidence.

No network access, new evidence, task detection, or LLM calls. Task weights are
provisional product policy, not empirically optimal or official AA benchmarks.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field

from tools.artificial_analysis import GENERAL, numeric
from tools.model_evidence import DOMAIN_INDICES, OPERATIONAL_FIELDS

POLICY_VERSION = "modelmatch-decision-v1"
TASK_DEFAULTS = {
    "general_assistant": 0.70,
    "tool_agent": 0.50,
    "reasoning_analysis": 0.50,
    "coding_assistant": 0.40,
    "specialized_domain": 0.30,
    "mixed_or_unknown": 0.60,
}
PENALTY_CAPS = {"cost": 8.0, "ttft": 5.0, "output_speed": 2.0}
PENALTY_METRICS = {"cost": "monthly_cost_usd", "ttft": "ttft", "output_speed": "output_speed"}
ASSUMPTIONS = [
    "G and U are original index points, not accuracy percentages; S is custom decision utility, not an official AA benchmark.",
    "Task-type weight defaults are provisional product policy, not validated optimum weights.",
    "Only explicitly supplied requirements affect penalties or eligibility.",
    "Performance comparisons use performance_v3 means only; mean TTFT does not establish P95 latency or an SLA.",
    "Monthly cost is a token-price estimate; provider, cache, reasoning-token and workload effects may differ.",
    "Observed evidence does not establish task relevance, current freshness, or verified deployment specifications.",
    "Capability Index versions may be unavailable; Intelligence Index version is not substituted for them.",
    "Eligible means no supplied hard constraint is known to fail or remain unknown, not universal production readiness.",
]


def _alpha(value: float) -> float:
    if not numeric(value) or not 0 <= value <= 1:
        raise ValueError("Alpha must be a finite number between 0 and 1, not a boolean.")
    return float(value)


@dataclass(frozen=True)
class WeightPolicy:
    task_defaults: dict[str, float] = field(default_factory=lambda: dict(TASK_DEFAULTS))
    fallback_alpha: float = 0.60

    def __post_init__(self):
        if any(not isinstance(key, str) or not key for key in self.task_defaults):
            raise ValueError("Task default names must be nonempty strings.")
        object.__setattr__(self, "task_defaults", {k: _alpha(v) for k, v in self.task_defaults.items()})
        object.__setattr__(self, "fallback_alpha", _alpha(self.fallback_alpha))


def resolve_weights(task_type: str | None = None, user_alpha: float | None = None,
                    *, policy: WeightPolicy | None = None) -> dict:
    """Resolve task suggestion, user override and fallback without detecting a task."""
    if task_type is not None and not isinstance(task_type, str):
        raise ValueError("Task type must be a string or None.")
    policy = policy or WeightPolicy()
    recognized = task_type in policy.task_defaults
    suggested = policy.task_defaults[task_type] if recognized else policy.fallback_alpha
    default_mode = "task_default" if recognized else "fallback_default"
    mode = default_mode if user_alpha is None else "user_override"
    selected = suggested if user_alpha is None else _alpha(user_alpha)
    return {
        "task_type": task_type, "alpha": selected, "use_case_weight": 1 - selected,
        "weight_mode": mode,
        "source": f"task_defaults.{task_type}" if mode == "task_default" else mode,
        "suggested_alpha": suggested, "suggested_weight_mode": default_mode,
        "default_policy_is_provisional": True, "policy_version": POLICY_VERSION,
    }


def weight_controls(weights: dict) -> dict:
    """Serializable interface for future task display, slider and reset controls."""
    suggested = weights["suggested_alpha"]
    return {
        "detected_task_type": weights["task_type"],
        "task_detection_source": "caller_supplied; no detection performed by this engine",
        "suggested_weights": {"general": suggested, "use_case": 1 - suggested},
        "selected_weights": {"general": weights["alpha"], "use_case": weights["use_case_weight"]},
        "weight_mode": weights["weight_mode"], "weight_source": weights["source"],
        "slider": {"min": 0.0, "max": 1.0, "step": 0.01, "value": weights["alpha"], "request_field": "user_alpha"},
        "reset_to_default": {"task_type": weights["task_type"], "user_alpha": None,
                             "alpha": suggested, "weight_mode": weights["suggested_weight_mode"]},
        "policy_note": "Suggested weights are provisional product defaults, not empirically validated optima.",
    }


def capped_linear_penalty(actual: float, target: float, cap: float, *, minimum: bool = False) -> float:
    """Deduct cap * min(1, relative violation). A minimum uses a shortfall.

    Zero upper targets: zero actual passes, any positive actual deducts the cap.
    Zero minimum targets are satisfied by every valid nonnegative measurement.
    This helper never interprets missing evidence as a zero deduction.
    """
    if any(not numeric(v) or v < 0 for v in (actual, target, cap)):
        raise ValueError("Penalty inputs must be finite, nonnegative numbers.")
    if target == 0:
        return 0.0 if minimum or actual == 0 else -float(cap)
    if (minimum and actual >= target) or (not minimum and actual <= target):
        return 0.0
    ratio = (target - actual) / target if minimum else (actual - target) / target
    return -float(cap) * min(1.0, ratio)


def _validate_prepared(prepared: dict) -> None:
    """Reject cross-model/snapshot joins rather than silently recombining evidence."""
    evidence = prepared["evidence"]
    for model_id, candidate in prepared["candidates"].items():
        if candidate["model_id"] != model_id:
            raise ValueError("Candidate key must equal its exact AA model ID.")
        for role in ("A", "B", "C"):
            if model_id not in prepared["researcher_evidence"][role]:
                raise ValueError("Missing researcher result for an AA model ID.")
        c = prepared["researcher_evidence"]["C"][model_id]
        if c["eligibility"] != candidate["eligibility"]:
            raise ValueError("Candidate and C eligibility disagree.")
        for eid in candidate["evidence_ids"]:
            e = evidence.get(eid)
            if e is None or e["evidence_id"] != eid or e["model_id"] != model_id:
                raise ValueError("Evidence ID/model join is invalid.")
            if e["snapshot_id"] != prepared["snapshot_id"] or e["data_mode"] != prepared["data_mode"]:
                raise ValueError("Evidence from different snapshots or data modes cannot be combined.")
        for check in c["checks"]:
            if check["evidence_id"] not in candidate["evidence_ids"]:
                raise ValueError("Operational check must reference this candidate's evidence.")


def _valid_index(prepared: dict, model_id: str, role: str, value, metric: str | None) -> bool:
    result = prepared["researcher_evidence"][role][model_id]
    if not result["valid"] or not numeric(value) or metric is None:
        return False
    return any(
        prepared["evidence"][eid]["metric"] == metric
        and prepared["evidence"][eid]["evidence_status"] == "observed"
        and numeric(prepared["evidence"][eid]["value"])
        and prepared["evidence"][eid]["value"] == value
        for eid in result["evidence_ids"]
        if eid in prepared["candidates"][model_id]["evidence_ids"]
    )


def _measurement(prepared: dict, model_id: str, check: dict) -> dict | None:
    e = prepared["evidence"][check["evidence_id"]]
    if not check["measurement_available"] or e["evidence_status"] != "observed" or not numeric(e["value"]) or e["value"] < 0:
        return None
    metric = check["metric"]
    if metric in ("ttft", "output_speed"):
        if e["metric"] != OPERATIONAL_FIELDS[metric][0] or e["statistic"] != "mean":
            return None
    if metric == "monthly_cost_usd":
        c = prepared["researcher_evidence"]["C"][model_id]
        workload = c["workload"]
        if any(not numeric(workload.get(key)) or workload[key] < 0 for key in ("monthly_requests", "avg_input_tokens", "avg_output_tokens")):
            return None
        inputs = [prepared["evidence"].get(eid, {}) for eid in e.get("input_evidence_ids", ())]
        expected = {OPERATIONAL_FIELDS[key][0] for key in ("input_price", "output_price")}
        if e["metric"] != metric or e["source_type"] != "derived" or len(inputs) != 2:
            return None
        if {i.get("metric") for i in inputs} != expected or any(
            i.get("model_id") != model_id or i.get("snapshot_id") != prepared["snapshot_id"]
            or i.get("evidence_status") != "observed" or not numeric(i.get("value")) or i["value"] < 0
            for i in inputs
        ):
            return None
    return e


def _penalties(prepared: dict, model_id: str) -> tuple[dict, float | None, list[str]]:
    c = prepared["researcher_evidence"]["C"][model_id]
    checks = {check["metric"]: check for check in c["checks"]}
    breakdown, blockers = {}, []
    for name, metric in PENALTY_METRICS.items():
        check = checks.get(metric)
        component = {"cap": PENALTY_CAPS[name], "status": "not_applicable", "deduction": 0.0,
                     "measurement": None, "target": None, "evidence_ids": [],
                     "formula": "-cap * min(1, max(0, (target - actual) / target))" if name == "output_speed" else "-cap * min(1, max(0, (actual - target) / target))"}
        if check is None:
            component["reason"] = "requirement_not_provided"
        elif check["hard"]:
            component["reason"] = "hard_constraint_handled_separately"
            component["target"] = check["target"]
            component["evidence_ids"] = [check["evidence_id"]]
        elif check["target"] is None:
            component["reason"] = "measurement_requested_without_penalty_target"
            component["evidence_ids"] = [check["evidence_id"]]
        else:
            component["target"] = check["target"]
            component["evidence_ids"] = [check["evidence_id"]]
            e = _measurement(prepared, model_id, check)
            if e is None:
                component.update(status="unknown", deduction=None, reason="missing_or_incompatible_measurement")
                blockers.append(f"unknown_{name}_penalty")
            else:
                component.update(status="applied", measurement=e["value"],
                                 deduction=capped_linear_penalty(e["value"], check["target"], PENALTY_CAPS[name], minimum=name == "output_speed"),
                                 reason="capped_linear_relative_violation")
                component["evidence_ids"] += list(e.get("input_evidence_ids", ()))
                if check["target"] == 0:
                    component["reason"] = "zero_target_boundary_rule"
        breakdown[name] = component
    # An unknown requested metric is not equivalent to a free operational pass.
    if not c["valid"]:
        blockers.append("requested_operational_evidence_incomplete")
    for check in c["checks"]:
        if not check["hard"] and check["target"] is not None and check["metric"] not in PENALTY_METRICS.values():
            blockers.append(f"no_soft_penalty_policy_for_{check['metric']}")
    total = None if blockers else max(-15.0, min(0.0, math.fsum(item["deduction"] for item in breakdown.values())))
    return breakdown, total, blockers


def _rank(candidates: dict, status: str) -> list[dict]:
    ordered = sorted((c for c in candidates.values() if c["candidate_status"] == status and c["S"] is not None),
                     key=lambda c: (-c["S"], c["model_id"]))
    result, previous, rank = [], None, 0
    for position, c in enumerate(ordered, 1):
        if c["S"] != previous:
            rank = position
        result.append({"model_id": c["model_id"], "rank": rank, "S": c["S"]})
        previous = c["S"]
    return result


def evaluate_operations(prepared: dict, model_ids: list[str] | None = None) -> dict:
    """Expose the existing operational rules to Researcher C without ranking.

    No G/U aggregation or sensitivity runs occur here. Final decide() remains
    exclusively after Lead Evidence Review in the orchestration pipeline.
    """
    _validate_prepared(prepared)
    results = {}
    for model_id in sorted(prepared["candidates"] if model_ids is None else model_ids):
        if model_id not in prepared["candidates"]:
            raise ValueError("Unknown AA model ID in operational evaluation.")
        breakdown, adjustment, blockers = _penalties(prepared, model_id)
        c = prepared["researcher_evidence"]["C"][model_id]
        cost = next((prepared["evidence"][check["evidence_id"]] for check in c["checks"] if check["metric"] == "monthly_cost_usd"), None)
        results[model_id] = {"O": adjustment, "operational_penalties": breakdown,
                             "constraint_checks": deepcopy(c["checks"]), "eligibility": c["eligibility"],
                             "estimated_monthly_cost_usd": cost["value"] if cost and cost["evidence_status"] == "observed" else None,
                             "operational_blockers": blockers}
    return results


def _apply_alpha(base: dict, alpha: float) -> dict:
    result = dict(base)
    result["S"] = None
    if not result["score_blockers"]:
        try:
            score = math.fsum((alpha * result["G"], (1 - alpha) * result["U"], result["O"]))
        except OverflowError:
            score = float("inf")
        if math.isfinite(score):
            result["S"] = score
        else:
            result["score_blockers"] = ["nonfinite_score"]
    result["score_status"] = "computed" if result["S"] is not None else "not_computable"
    return result


def decide(prepared: dict, *, task_type: str | None = None, user_alpha: float | None = None,
           weight_policy: WeightPolicy | None = None) -> dict:
    """Score ALL prepared candidates, not only Phase 2A display shortlists.

    Fully-evaluable and provisional rankings stay separate. Ineligible/unverified
    candidates have no S. Sensitivity reuses the same evidence and penalties.
    """
    _validate_prepared(prepared)
    weights = resolve_weights(task_type, user_alpha, policy=weight_policy)
    domain = prepared["relevance"]["domain"]
    u_metric = f"evaluations.{DOMAIN_INDICES[domain]}" if domain in DOMAIN_INDICES else None
    bases = {}
    for model_id, candidate in sorted(prepared["candidates"].items()):
        breakdown, adjustment, blockers = _penalties(prepared, model_id)
        if not _valid_index(prepared, model_id, "A", candidate["G"], f"evaluations.{GENERAL}"):
            blockers.append("missing_or_invalid_G")
        if not _valid_index(prepared, model_id, "B", candidate["U"], u_metric):
            blockers.append("missing_or_invalid_U")
        if candidate["eligibility"] != "eligible":
            blockers.append(f"hard_constraints_{candidate['eligibility']}")
        c = prepared["researcher_evidence"]["C"][model_id]
        cost = next((prepared["evidence"][check["evidence_id"]] for check in c["checks"] if check["metric"] == "monthly_cost_usd"), None)
        bases[model_id] = {
            "model_id": model_id, "name": candidate["name"], "G": candidate["G"], "U": candidate["U"],
            "O": adjustment, "operational_penalties": breakdown, "weights": dict(weights),
            "candidate_status": candidate["candidate_status"], "eligibility": candidate["eligibility"],
            "evidence_completeness": dict(candidate["evidence_completeness"]),
            "constraint_checks": deepcopy(c["checks"]), "workload": dict(c["workload"]),
            "estimated_monthly_cost_usd": cost["value"] if cost and cost["evidence_status"] == "observed" else None,
            "evidence_ids": list(candidate["evidence_ids"]), "snapshot_id": prepared["snapshot_id"],
            "retrieved_at": prepared["retrieved_at"], "data_mode": prepared["data_mode"],
            "assumptions": list(ASSUMPTIONS), "score_blockers": sorted(set(blockers)),
        }
    candidates = {mid: _apply_alpha(base, weights["alpha"]) for mid, base in bases.items()}
    rankings = {status: _rank(candidates, status) for status in ("fully_evaluable", "provisional")}
    sensitivity = []
    for alpha in sorted({0.50, 0.60, 0.70, weights["alpha"]}):
        scenario = {mid: _apply_alpha(base, alpha) for mid, base in bases.items()}
        by_status = {status: _rank(scenario, status) for status in rankings}
        changes = {}
        for status, ranking in by_status.items():
            actual_ranks = {r["model_id"]: r["rank"] for r in rankings[status]}
            changes[status] = [{"model_id": r["model_id"], "rank": r["rank"],
                                "actual_alpha_rank": actual_ranks.get(r["model_id"]),
                                "rank_delta": actual_ranks[r["model_id"]] - r["rank"] if r["model_id"] in actual_ranks else None}
                               for r in ranking]
        sensitivity.append({"alpha": alpha, "is_actual_alpha": alpha == weights["alpha"],
                            "rankings": by_status, "rank_changes": changes})
    return {
        "policy_version": POLICY_VERSION, "formula": "S = alpha * G + (1 - alpha) * U + O",
        "weights": weights, "weight_controls": weight_controls(weights),
        "snapshot_id": prepared["snapshot_id"], "retrieved_at": prepared["retrieved_at"],
        "data_mode": prepared["data_mode"], "catalog_complete": prepared["catalog_complete"],
        "counts_before_shortlist": dict(prepared["counts_before_shortlist"]),
        "candidates": candidates, "rankings": rankings, "sensitivity": sensitivity,
        "missing_manifest": deepcopy(prepared["missing_manifest"]),
        "evidence": deepcopy(prepared["evidence"]), "relevance": dict(prepared["relevance"]),
        "assumptions": list(ASSUMPTIONS),
    }
