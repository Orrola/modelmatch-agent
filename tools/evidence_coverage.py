"""Unranked evidence coverage and Potential Alternatives; no scoring or selection."""

from collections import Counter
from copy import deepcopy

from tools.artificial_analysis import GENERAL, MISSING, get_path, numeric
from tools.decision import _validate_prepared
from tools.model_evidence import DOMAIN_INDICES
from tools.model_metadata import snapshot_binding

COVERAGE_VERSION = "evidence-coverage-v2"


def _validate_inputs(snapshot, prepared, metadata, decision):
    rows, binding = snapshot_binding(snapshot)
    if any(metadata.get(k) != value for k, value in binding.items()):
        raise ValueError("Identity metadata belongs to a different snapshot.")
    expected = set(rows)
    for data in (prepared, decision):
        if any(data.get(k) != binding[k] for k in ("snapshot_id", "data_mode", "retrieved_at")):
            raise ValueError("Coverage cannot combine different snapshots or retrievals.")
        if set(data["candidates"]) != expected:
            raise ValueError("Coverage must retain the complete source candidate universe.")
    if set(metadata["models"]) != expected:
        raise ValueError("Identity metadata must retain every exact source model ID.")
    _validate_prepared(prepared)
    if (decision["evidence"] != prepared["evidence"] or decision["relevance"] != prepared["relevance"]
            or decision["missing_manifest"] != prepared["missing_manifest"]):
        raise ValueError("Decision and prepared evidence do not match.")
    for evidence in prepared["evidence"].values():
        if (evidence["snapshot_id"] != binding["snapshot_id"] or evidence["data_mode"] != binding["data_mode"]
                or evidence["model_id"] not in expected):
            raise ValueError("Evidence contains a foreign snapshot or model identity.")
        if evidence["source_type"] == "artificial_analysis":
            raw = get_path(rows[evidence["model_id"]][0], evidence["metric"])
            if (evidence["value"] != (None if raw is MISSING else raw)
                    or evidence["retrieved_at"] != binding["retrieved_at"]
                    or evidence["source_url"] != binding["source_url"]):
                raise ValueError("AA evidence does not match its bound source snapshot.")
        for input_id in evidence.get("input_evidence_ids", []):
            source = prepared["evidence"].get(input_id)
            if source is None or source["model_id"] != evidence["model_id"]:
                raise ValueError("Derived evidence has an invalid source reference.")
    for model_id, (row, _) in rows.items():
        meta, candidate = metadata["models"][model_id], prepared["candidates"][model_id]
        result = decision["candidates"][model_id]
        creator = row.get("model_creator") if isinstance(row.get("model_creator"), dict) else {}
        if (meta["model_id"] != model_id or meta["snapshot_id"] != binding["snapshot_id"]
                or meta["original_name"] != row.get("name") or meta["original_slug"] != row.get("slug")
                or meta["release_date"] != row.get("release_date") or meta["creator_id"] != creator.get("id")
                or meta["creator_name"] != creator.get("name")):
            raise ValueError("Identity metadata exact-ID join is invalid.")
        for key in ("model_id", "name", "G", "U", "eligibility", "candidate_status", "evidence_ids"):
            if result[key] != candidate[key]:
                raise ValueError("Decision candidate does not match the prepared evidence.")
    return rows, binding


def _index(prepared, model_id, role, metric, source_value):
    role_data = prepared["researcher_evidence"][role][model_id]
    records = [prepared["evidence"][eid] for eid in role_data["evidence_ids"]]
    available = bool(role_data["valid"] and metric and numeric(source_value) and any(
        e["metric"] == metric and e["evidence_status"] == "observed" and e["value"] == source_value for e in records))
    return {"available": available, "metric": metric, "value": source_value if available else None,
            "evidence_ids": list(role_data["evidence_ids"]),
            "evidence_statuses": sorted({e["evidence_status"] for e in records})}


def analyze_evidence_coverage(snapshot, prepared, metadata, decision):
    """Consume an existing Decision; never calculate, repair or replace G/U/O/S."""
    rows, binding = _validate_inputs(snapshot, prepared, metadata, decision)
    domain = prepared["relevance"]["domain"]
    g_metric = f"evaluations.{GENERAL}"
    u_metric = f"evaluations.{DOMAIN_INDICES[domain]}" if domain in DOMAIN_INDICES else None
    missing = {m["model_id"]: m["missing_fields"] for m in prepared["missing_manifest"]}
    models, alternatives = {}, {key: [] for key in ("eligible", "unverified", "ineligible")}
    for model_id, (row, _) in sorted(rows.items()):
        g = _index(prepared, model_id, "A", g_metric, get_path(row, g_metric))
        u = _index(prepared, model_id, "B", u_metric, get_path(row, u_metric) if u_metric else None)
        candidate = decision["candidates"][model_id]
        operations = prepared["researcher_evidence"]["C"][model_id]
        complete = g["available"] and u["available"] and operations["valid"]
        score = candidate["S"]
        if (score is None and candidate["score_status"] == "computed") or (score is not None and candidate["score_status"] != "computed"):
            raise ValueError("Decision score and score status disagree.")
        if score is not None and (not complete or not numeric(score) or candidate["eligibility"] != "eligible"):
            raise ValueError("A Decision score conflicts with evidence availability or eligibility.")
        official = [prepared["evidence"][check["evidence_id"]] for check in operations["checks"]
                    if prepared["evidence"][check["evidence_id"]]["source_type"] in ("official_docs", "official_docs_pending")]
        official_verified = [e for e in official if e["evidence_status"] == "observed"
                             and e.get("verification_status") == "verified"]
        verification = {"benchmark_evidence": "synthetic_fixture" if binding["data_mode"] == "mock" else "aa_observed_only",
            "provider": "unknown",
            "official_specifications": "not_requested" if not official else "verified" if len(official_verified) == len(official)
                and binding["data_mode"] == "live" else "unknown",
            "official_evidence_ids": [e["evidence_id"] for e in official]}
        reasons = deepcopy(missing.get(model_id, []))
        entry = {"model_id": model_id, "snapshot_id": binding["snapshot_id"], "G": g, "U": u,
            "scoring_completeness": {"indices_complete": g["available"] and u["available"],
                "operational_evidence_complete": operations["valid"], "evidence_complete": complete,
                "policy_supported": not any(b.startswith("no_soft_penalty_policy_for_") for b in candidate["score_blockers"])},
            "eligibility": candidate["eligibility"], "candidate_status": candidate["candidate_status"],
            "constraint_checks": deepcopy(candidate["constraint_checks"]), "verification": verification,
            "missing_evidence_reasons": reasons, "decision_score_status": candidate["score_status"],
            "decision_score_available": score is not None, "decision_S": score,
            "score_blockers": list(candidate["score_blockers"]), "evidence_ids": list(candidate["evidence_ids"])}
        models[model_id] = entry
        if not complete:
            alternatives[candidate["eligibility"]].append({"model_id": model_id,
                "snapshot_id": binding["snapshot_id"], "name": metadata["models"][model_id]["original_name"],
                "G_available": g["available"],
                "U_available": u["available"], "scoring_evidence_complete": False,
                "eligibility": candidate["eligibility"], "candidate_status": candidate["candidate_status"],
                "verification": deepcopy(verification), "missing_evidence_reasons": deepcopy(reasons),
                "evidence_ids": list(candidate["evidence_ids"]), "score_blockers": list(candidate["score_blockers"]),
                "S": None, "representation_status": "unranked_incomplete_evidence_not_a_recommendation"})
    return {"coverage_version": COVERAGE_VERSION, "metadata_version": metadata["metadata_version"],
        **binding, "relevance": deepcopy(prepared["relevance"]),
        "models": models, "counts": {"total": len(models),
            "G_available": sum(e["G"]["available"] for e in models.values()),
            "U_available": sum(e["U"]["available"] for e in models.values()),
            "scoring_evidence_complete": sum(e["scoring_completeness"]["evidence_complete"] for e in models.values()),
            "decision_score_available": sum(e["decision_score_available"] for e in models.values()),
            "eligibility": dict(Counter(e["eligibility"] for e in models.values())),
            "potential_alternatives": {key: len(value) for key, value in alternatives.items()}},
        "potential_alternatives": {"source_version": COVERAGE_VERSION, "snapshot_id": binding["snapshot_id"],
            "ranked": False, "policy": "Source records only. Hard violations remain ineligible; unknown hard evidence "
                "remains unverified. No recommendation, replacement score or selection is implied.",
            "by_eligibility": alternatives}}
