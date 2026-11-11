"""Phase 2A: snapshot-only evidence and candidate preparation; NO scoring.

The future Lead/Researcher B supplies an explicit relevance decision. This module
does not infer task relevance from industry keywords or call Gemini/the network.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from typing import Any

from tools.artificial_analysis import GENERAL, MISSING, get_path, numeric, validate_page

DOMAIN_INDICES = {
    "finance": "artificial_analysis_finance_and_accounting_index",
    "strategy_operations": "artificial_analysis_strategy_and_ops_index",
    "legal": "artificial_analysis_legal_index",
    "healthcare": "artificial_analysis_healthcare_and_medical_index",
    "engineering": "artificial_analysis_engineering_index",
    "economics": "artificial_analysis_economics_index",
}
METHODOLOGY_URL = "https://artificialanalysis.ai/methodology/capability-indices"
OPERATIONAL_FIELDS = {
    "input_price": ("pricing.price_1m_input_tokens", "USD/1M input tokens", None),
    "output_price": ("pricing.price_1m_output_tokens", "USD/1M output tokens", None),
    "ttft": ("performance_v3.mean_time_to_first_token_seconds", "seconds", "mean"),
    "output_speed": ("performance_v3.mean_output_tokens_per_second", "tokens/second", "mean"),
}
STATUSES = ("fully_evaluable", "provisional", "ineligible", "unverified")


@dataclass(frozen=True)
class RelevanceDecision:
    use_case: str
    domain: str | None
    match_status: str
    rationale: str
    methodology_url: str = METHODOLOGY_URL

    def __post_init__(self):
        if not self.use_case.strip() or not self.rationale.strip() or not self.methodology_url.strip():
            raise ValueError("Use case, relevance rationale and methodology URL must be documented.")
        if self.match_status not in ("strong", "partial", "none"):
            raise ValueError("match_status must be strong, partial or none.")
        if self.match_status != "none" and self.domain not in DOMAIN_INDICES:
            raise ValueError("A supported AA domain is required for strong/partial relevance.")
        if self.match_status == "none" and self.domain is not None:
            raise ValueError("Unsupported use cases must use domain=None; do not invent U.")


@dataclass(frozen=True)
class OperationalRequirement:
    """ttft and speed comparisons require mean; unknown metrics await evidence.

monthly_cost_usd requires workload and both prices. Other requirements (including
context_window, deployment, data_residency) intentionally remain unknown in 2A.
"""

    metric: str
    target: Any = None
    hard: bool = False
    statistic: str | None = None

    def __post_init__(self):
        if not self.metric.strip():
            raise ValueError("Requirement metric must not be empty.")
        if self.metric in (*OPERATIONAL_FIELDS, "monthly_cost_usd"):
            if self.target is not None and (not numeric(self.target) or self.target < 0):
                raise ValueError("Operational numeric targets must be finite and nonnegative.")
            if self.hard and self.target is None:
                raise ValueError("A hard numeric constraint needs an explicit target.")


@dataclass(frozen=True)
class Workload:
    monthly_requests: float | None = None
    avg_input_tokens: float | None = None
    avg_output_tokens: float | None = None

    def __post_init__(self):
        for value in asdict(self).values():
            if value is not None and (not numeric(value) or value < 0):
                raise ValueError("Workload values must be finite and nonnegative, or None.")


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    model_id: str
    metric: str
    value: Any
    unit: str | None
    statistic: str | None
    source_type: str
    source_url: str | None
    snapshot_id: str
    retrieved_at: str | None
    index_version: Any
    evidence_status: str
    reason: str | None
    data_mode: str
    input_evidence_ids: tuple[str, ...] = ()
    supporting_excerpt: str | None = None
    verification_status: str | None = None
    exact_model_version: str | None = None


def _record(snapshot, model_id, metric, value, *, unit=None, statistic=None,
            version=None, status=None, reason=None, source_type="artificial_analysis",
            inputs=(), nonnegative=False, source_url=MISSING) -> EvidenceRecord:
    if status is None:
        if value is MISSING:
            status, reason = "missing", "field_absent"
        elif value is None:
            status, reason = "missing", "value_null"
        elif not numeric(value):
            status, reason = "invalid", "not_a_finite_number"
        elif nonnegative and value < 0:
            status, reason = "invalid", "negative_operational_value"
        else:
            status = "observed"
    # NaN/Infinity are recorded as invalid, never emitted as non-standard JSON.
    stored = None if value is MISSING or (isinstance(value, float) and not numeric(value)) else value
    identity = f"{snapshot['snapshot_id']}:{model_id}:{metric}"
    if source_url is MISSING:
        source_url = None if source_type == "official_docs_pending" else snapshot["source_url"]
    return EvidenceRecord(
        hashlib.sha256(identity.encode()).hexdigest()[:24], model_id, metric, stored,
        unit, statistic, source_type,
        source_url,
        snapshot["snapshot_id"], snapshot.get("retrieved_at"),
        version, status, reason, snapshot["data_mode"], tuple(inputs),
    )


def _snapshot_rows(snapshot: dict) -> dict[str, tuple[dict, Any]]:
    """Join key is the exact AA ID; duplicate IDs/version conflicts fail closed."""
    for field in ("snapshot_id", "source_url", "data_mode"):
        if not snapshot.get(field):
            raise ValueError(f"Snapshot requires {field}.")
    if snapshot["data_mode"] not in ("live", "mock"):
        raise ValueError("Snapshot data mode must be live or mock.")
    if snapshot["data_mode"] == "live" and not snapshot.get("retrieved_at"):
        raise ValueError("Live snapshot requires a retrieval timestamp.")
    rows = {}
    pages = snapshot.get("pages", [])
    if not pages:
        raise ValueError("Snapshot must contain at least one page.")
    first_version = pages[0].get("intelligence_index_version")
    for number, page in enumerate(pages, 1):
        validate_page(page, number)
        if page["intelligence_index_version"] != first_version:
            raise ValueError("Mixed Intelligence Index versions in one snapshot.")
        if page["tier"] != pages[0]["tier"]:
            raise ValueError("Mixed API tiers in one snapshot.")
        if number < len(pages) and not page["pagination"]["has_more"]:
            raise ValueError("Snapshot pagination ends before its last page.")
        for row in page["data"]:
            if row["id"] in rows:
                raise ValueError("Duplicate AA model ID; evidence join rejected.")
            rows[row["id"]] = (row, page["intelligence_index_version"])
    return rows


def build_candidates(
    snapshot: dict,
    relevance: RelevanceDecision,
    requirements: tuple[OperationalRequirement, ...] = (),
    *,
    workload: Workload | None = None,
    shortlist_size: int | None = 20,
    official_evidence: dict | None = None,
) -> dict:
    """Use ONE shared snapshot. Return all candidates/manifest before shortlisting.

    Shortlist size applies PER status. Selection rotates creators, starting from
    raw selected-domain U (then G). It is retrieval priority, not final ranking.
    No penalty, alpha, score, sensitivity or weighted aggregation exists here.
    """
    if shortlist_size is not None and (type(shortlist_size) is not int or shortlist_size < 0):
        raise ValueError("shortlist_size must be a nonnegative integer or None.")
    if len({r.metric for r in requirements}) != len(requirements):
        raise ValueError("Duplicate operational requirement metrics are ambiguous.")
    rows = _snapshot_rows(snapshot)
    workload = workload or Workload()
    a, b, c, evidence, manifest = {}, {}, {}, {}, []
    requirements_by_metric = {r.metric: r for r in requirements}

    for model_id, (row, version) in sorted(rows.items()):
        issues, records = [], {}

        def add(record, role, required):
            evidence[record.evidence_id] = asdict(record)
            records[record.metric] = record
            if record.evidence_status != "observed":
                issues.append({"role": role, "metric": record.metric, "reason": record.reason,
                               "evidence_status": record.evidence_status,
                               "required": required, "evidence_id": record.evidence_id})
            return record

        g_path = f"evaluations.{GENERAL}"
        g = add(_record(snapshot, model_id, g_path, get_path(row, g_path),
                        unit="index_points", version=version), "A", True)
        a[model_id] = {"valid": g.evidence_status == "observed", "G": g.value,
                       "evidence_ids": [g.evidence_id]}
        if relevance.domain is not None:
            u_path = f"evaluations.{DOMAIN_INDICES[relevance.domain]}"
            # The Intelligence Index version is NOT the Capability Index version.
            u = add(_record(snapshot, model_id, u_path, get_path(row, u_path),
                            unit="index_points"), "B", True)
        else:
            u = add(_record(snapshot, model_id, "use_case_index", None, unit="index_points",
                            status="unknown", reason="no_supported_relevant_index", source_type="relevance_decision",
                            source_url=relevance.methodology_url), "B", True)
        b[model_id] = {"valid": u.evidence_status == "observed" and relevance.match_status != "none",
                       "U": u.value, "relevance": asdict(relevance), "evidence_ids": [u.evidence_id]}
        ops = {}
        for metric, (path, unit, statistic) in OPERATIONAL_FIELDS.items():
            required = metric in requirements_by_metric or (
                metric in ("input_price", "output_price") and "monthly_cost_usd" in requirements_by_metric)
            ops[metric] = add(_record(snapshot, model_id, path, get_path(row, path),
                                     unit=unit, statistic=statistic, nonnegative=True), "C", required)

        checks = []
        for requirement in requirements:
            metric = requirement.metric
            if metric == "monthly_cost_usd":
                missing_workload = [key for key, value in asdict(workload).items() if value is None]
                prices = [ops["input_price"], ops["output_price"]]
                inputs = [p.evidence_id for p in prices]
                if missing_workload or any(p.evidence_status != "observed" for p in prices):
                    reason = "missing_workload:" + ",".join(missing_workload) if missing_workload else "missing_or_invalid_token_prices"
                    record = _record(snapshot, model_id, metric, None, unit="USD/month",
                                     status="unknown", reason=reason, source_type="derived", inputs=inputs)
                else:
                    cost = workload.monthly_requests * (
                        workload.avg_input_tokens * prices[0].value + workload.avg_output_tokens * prices[1].value
                    ) / 1_000_000
                    record = _record(snapshot, model_id, metric, cost, unit="USD/month",
                                     source_type="derived", inputs=inputs, nonnegative=True)
                record = add(record, "C", True)
            elif metric in ops:
                record = ops[metric]
            else:
                # No speculative context/deployment data, even if an unverified raw
                # API extension happens to contain a similarly named field.
                from tools.official_specs import SpecEvidence
                spec = (official_evidence or {}).get(model_id, {}).get(metric)
                if (isinstance(spec, SpecEvidence) and spec.verification_status == "verified"
                    and spec.model_id == model_id and spec.snapshot_id == snapshot["snapshot_id"]
                    and spec.metric == metric and spec.source_url and spec.excerpt and spec.exact_version
                    and (snapshot["data_mode"] == "mock" or spec.verification_mode == "live")):
                    record = _record(snapshot, model_id, metric, spec.value,
                        unit="tokens" if metric in ("context_window", "max_input_tokens", "max_output_tokens") else None,
                        status="observed", source_type="official_docs", source_url=spec.source_url)
                    record = replace(record, retrieved_at=spec.retrieved_at, supporting_excerpt=spec.excerpt,
                                     verification_status=spec.verification_status, exact_model_version=spec.exact_version)
                else:
                    record = _record(snapshot, model_id, metric, None, status="unknown",
                                     reason=spec.reason if isinstance(spec, SpecEvidence) else "official_verification_not_implemented",
                                     source_type="official_docs_pending")
                record = add(record, "C", True)
            compatible = metric not in ("ttft", "output_speed") or requirement.statistic in (None, "mean")
            available = record.evidence_status == "observed" and compatible
            if not compatible:
                issues.append({"role": "C", "metric": record.metric,
                               "reason": "requested_statistic_incompatible_with_v3_mean",
                               "evidence_status": "unknown", "required": True,
                               "evidence_id": record.evidence_id})
            state = "unknown"
            if available:
                state = "pass"
                if requirement.target is not None:
                    if numeric(record.value) and numeric(requirement.target):
                        minimum_capacity = metric in ("output_speed", "context_window", "max_input_tokens", "max_output_tokens")
                        meets = record.value >= requirement.target if minimum_capacity else record.value <= requirement.target
                        state = "pass" if meets else "fail"
                    elif isinstance(record.value, str) and isinstance(requirement.target, str):
                        # A different documented deployment option does not prove
                        # that the requested option is unavailable.
                        state = "pass" if record.value.casefold() == requirement.target.casefold() else "unknown"
            checks.append({"metric": metric, "hard": requirement.hard, "target": requirement.target,
                           "measurement_available": available, "constraint_status": state,
                           "evidence_id": record.evidence_id})
        hard_states = [check["constraint_status"] for check in checks if check["hard"]]
        eligibility = "ineligible" if "fail" in hard_states else "unverified" if "unknown" in hard_states else "eligible"
        c[model_id] = {"valid": all(check["measurement_available"] for check in checks),
                       "checks": checks, "eligibility": eligibility,
                       "workload": asdict(workload),
                       "evidence_ids": [r.evidence_id for r in records.values() if r.evidence_id not in a[model_id]["evidence_ids"] + b[model_id]["evidence_ids"]]}
        if issues:
            manifest.append({"model_id": model_id, "snapshot_id": snapshot["snapshot_id"], "missing_fields": issues})

    # Explicit dictionary lookup joins A/B/C by AA ID, never by list position.
    candidates = {}
    groups = {status: [] for status in STATUSES}
    for model_id in sorted(rows):
        completeness = {"A": a[model_id]["valid"], "B": b[model_id]["valid"], "C": c[model_id]["valid"]}
        eligibility = c[model_id]["eligibility"]
        if eligibility in ("ineligible", "unverified"):
            status = eligibility
        else:
            status = "fully_evaluable" if all(completeness.values()) and relevance.match_status == "strong" else "provisional"
        row = rows[model_id][0]
        creator = row.get("model_creator") or {}
        creator_id = creator.get("id", "unknown") if isinstance(creator, dict) else "unknown"
        candidates[model_id] = {
            "model_id": model_id, "name": row.get("name"), "creator_id": creator_id,
            "G": a[model_id]["G"], "U": b[model_id]["U"],
            "evidence_completeness": completeness, "eligibility": eligibility,
            "candidate_status": status,
            "evidence_ids": a[model_id]["evidence_ids"] + b[model_id]["evidence_ids"] + c[model_id]["evidence_ids"],
        }
        groups[status].append(model_id)

    shortlists = {}
    for status, ids in groups.items():
        def priority(model_id):
            candidate = candidates[model_id]
            return (-(candidate["U"] if b[model_id]["valid"] else float("-inf")),
                    -(candidate["G"] if a[model_id]["valid"] else float("-inf")), model_id)
        creators = {}
        for model_id in sorted(ids, key=priority):
            creators.setdefault(candidates[model_id]["creator_id"], []).append(model_id)
        chosen = []
        while creators and (shortlist_size is None or len(chosen) < shortlist_size):
            for creator in list(creators):
                chosen.append(creators[creator].pop(0))
                if not creators[creator]:
                    del creators[creator]
                if shortlist_size is not None and len(chosen) >= shortlist_size:
                    break
        shortlists[status] = chosen
    return {
        "snapshot_id": snapshot["snapshot_id"], "retrieved_at": snapshot.get("retrieved_at"),
        "data_mode": snapshot["data_mode"], "catalog_complete": not snapshot["pages"][-1]["pagination"]["has_more"],
        "relevance": asdict(relevance), "requirements": [asdict(r) for r in requirements],
        "counts_before_shortlist": {"total": len(candidates), **{s: len(ids) for s, ids in groups.items()},
                                    "A_valid": sum(v["valid"] for v in a.values()),
                                    "B_valid": sum(v["valid"] for v in b.values()),
                                    "C_valid": sum(v["valid"] for v in c.values())},
        "researcher_evidence": {"A": a, "B": b, "C": c}, "evidence": evidence,
        "missing_manifest": manifest, "candidates": candidates, "candidate_groups": groups,
        "shortlists": shortlists, "shortlist_size_per_status": shortlist_size,
        "selection_policy": "selected-domain U then G; creator round-robin; NOT final scoring/ranking",
    }
