"""Deterministic Best Overall and unranked exploration; never compute S."""

import hashlib
import json
from collections import Counter
from copy import deepcopy

from tools.artificial_analysis import numeric

SELECTOR_VERSION = "best-overall-selector-v2"


def _validate(decision, metadata, coverage):
    for key in ("snapshot_id", "data_mode", "retrieved_at"):
        if decision.get(key) != metadata.get(key) or coverage.get(key) != metadata.get(key):
            raise ValueError("Selector inputs belong to different snapshots or data modes.")
    for key in ("snapshot_fingerprint", "source_url", "metadata_version"):
        if not metadata.get(key) or coverage.get(key) != metadata[key]:
            raise ValueError("Selector metadata binding or version is inconsistent.")
    ids = set(decision["candidates"])
    if ids != set(metadata["models"]) or ids != set(coverage["models"]):
        raise ValueError("Selector requires the complete exact-ID candidate universe.")
    if coverage["relevance"] != decision["relevance"]:
        raise ValueError("Coverage uses a different task-index relevance decision.")
    if coverage["potential_alternatives"]["snapshot_id"] != decision["snapshot_id"]:
        raise ValueError("Potential Alternatives source belongs to a different snapshot.")
    for mid in sorted(ids):
        c, m, e = decision["candidates"][mid], metadata["models"][mid], coverage["models"][mid]
        if (c["eligibility"] not in ("eligible", "unverified", "ineligible")
                or c["candidate_status"] not in ("fully_evaluable", "provisional", "unverified", "ineligible")
                or (c["S"] is None and c["score_status"] == "computed")):
            raise ValueError("Selector eligibility or score status is invalid.")
        if any(x["model_id"] != mid or x["snapshot_id"] != decision["snapshot_id"] for x in (c, m, e)):
            raise ValueError("Selector model identity join is invalid.")
        if m["original_name"] != c["name"]:
            raise ValueError("Selector identity metadata does not match the Decision.")
        if (e["eligibility"] != c["eligibility"] or e["candidate_status"] != c["candidate_status"]
                or e["evidence_ids"] != c["evidence_ids"] or e["decision_S"] != c["S"]
                or e["score_blockers"] != c["score_blockers"] or e["constraint_checks"] != c["constraint_checks"]
                or e["decision_score_status"] != c["score_status"]
                or e["decision_score_available"] != (c["S"] is not None)):
            raise ValueError("Selector coverage and Decision disagree.")
        for index in ("G", "U"):
            if not set(e[index]["evidence_ids"]) <= set(c["evidence_ids"]):
                raise ValueError("Index coverage references another candidate's evidence.")
            if e[index]["available"] and (not numeric(c[index]) or e[index]["value"] != c[index]):
                raise ValueError("Available index does not match its original Decision value.")
            records = [decision["evidence"].get(eid, {}) for eid in e[index]["evidence_ids"]]
            if e[index]["available"] and not any(r.get("metric") == e[index]["metric"]
                    and r.get("evidence_status") == "observed" and r.get("value") == c[index] for r in records):
                raise ValueError("Index availability has no matching observed evidence.")
        for eid in c["evidence_ids"]:
            record = decision["evidence"].get(eid, {})
            if (record.get("model_id") != mid or record.get("snapshot_id") != decision["snapshot_id"]
                    or record.get("data_mode") != decision["data_mode"]):
                raise ValueError("Selector evidence contains a foreign model or snapshot.")
        if c["S"] is not None and (not numeric(c["S"]) or c["eligibility"] != "eligible"
                or not e["G"]["available"] or not e["U"]["available"]
                or not e["scoring_completeness"]["evidence_complete"] or c["score_status"] != "computed"):
            raise ValueError("A numeric score conflicts with eligibility or missing evidence.")
    for status in ("fully_evaluable", "provisional"):
        expected = sorted((mid for mid, c in decision["candidates"].items()
                           if c["candidate_status"] == status and c["S"] is not None),
                          key=lambda mid: (-decision["candidates"][mid]["S"], mid))
        ranks = decision["rankings"][status]
        if [r["model_id"] for r in ranks] != expected:
            raise ValueError("Raw rankings do not match the complete scored candidate cohort.")
        previous, rank = None, 0
        for position, row in enumerate(ranks, 1):
            score = decision["candidates"][row["model_id"]]["S"]
            if score != previous:
                rank = position
            if row["S"] != score or row["rank"] != rank:
                raise ValueError("Raw score or competition rank is inconsistent.")
            previous = score


def _unavailable(code, **details):
    return {"status": "unavailable", "reason_code": code, "details": details, "candidate": None}


def _exploration(coverage, metadata, limit):
    buckets = {kind: {state: [] for state in ("eligible", "unverified")} for kind in ("U_only", "G_only")}
    excluded = Counter()
    for mid, e in sorted(coverage["models"].items()):
        g, u = e["G"]["available"], e["U"]["available"]
        if e["eligibility"] == "ineligible":
            excluded["known_hard_constraint_violation"] += 1
        elif not g and not u:
            excluded["no_available_index_evidence"] += 1
        elif g and u:
            excluded["both_indices_available"] += 1
        else:
            kind = "G_only" if g else "U_only"
            buckets[kind][e["eligibility"]].append({"model_id": mid, "snapshot_id": e["snapshot_id"],
                "name": metadata["models"][mid]["original_name"],
                "available_index": deepcopy(e["G"] if g else e["U"]), "S": None,
                "eligibility": e["eligibility"], "candidate_status": e["candidate_status"],
                "verification": deepcopy(e["verification"]), "evidence_ids": list(e["evidence_ids"]),
                "missing_evidence_reasons": deepcopy(e["missing_evidence_reasons"]),
                "status": "unranked_exploration_not_a_recommendation"})
    return {"source_version": coverage["potential_alternatives"]["source_version"],
        "ranked": False, "task_relevance": deepcopy(coverage["relevance"]),
        "limit_per_evidence_and_eligibility_bucket": limit,
        "ordering": "exact_model_id_ascending; not an evidence-quality ranking",
        "positive_evidence_definition": "An available original task-relevant U or general G, including zero; no quality threshold is inferred.",
        "buckets": {kind: {state: {"total_before_limit": len(rows), "returned": len(rows[:limit]),
            "omitted": max(0, len(rows) - limit), "entries": rows[:limit]} for state, rows in states.items()}
            for kind, states in buckets.items()}, "excluded_counts_partition": dict(excluded)}


def select_recommendations(decision, metadata, coverage, *, potential_limit_per_bucket=5):
    """Assign roles without changing scores, eligibility, evidence or raw rankings."""
    if type(potential_limit_per_bucket) is not int or not 0 <= potential_limit_per_bucket <= 20:
        raise ValueError("Potential exploration limit must be an integer from 0 to 20.")
    _validate(decision, metadata, coverage)
    candidates = decision["candidates"]
    order = sorted((mid for mid, c in candidates.items() if c["eligibility"] == "eligible" and c["score_status"] == "computed" and numeric(c["S"])),
                   key=lambda mid: (-candidates[mid]["S"], mid))
    group = candidates[order[0]]["candidate_status"] if order else None
    ranking = decision["rankings"][group] if group else []
    ranks = {r["model_id"]: {"raw_rank": r["rank"], "raw_position": i} for i, r in enumerate(ranking, 1)}

    def selected(mid, reason, **details):
        c = candidates[mid]
        return {"status": "selected", "reason_code": reason, "details": details,
            "candidate": {**{k: deepcopy(c[k]) for k in ("model_id", "name", "G", "U", "O", "S",
                "candidate_status", "eligibility", "evidence_ids", "estimated_monthly_cost_usd")},
                **ranks[mid], "raw_ranking_group": group,
                "creator_id": metadata["models"][mid]["creator_id"],
                "creator_name": metadata["models"][mid]["creator_name"],
                "provider": deepcopy(metadata["models"][mid]["provider"]),
                "provider_status": metadata["models"][mid]["provider_status"]}}

    # Retired keys remain neutral for clients that still read the previous envelope.
    slots = {"best_overall": _unavailable("no_eligible_scored_candidate"),
             "lower_cost_alternative": _unavailable("recommendation_role_retired"),
             "different_family": _unavailable("recommendation_role_retired")}
    if order:
        slots["best_overall"] = selected(order[0], "highest_original_rank_in_cohort")
    entries = coverage["models"]
    g_count = sum(e["G"]["available"] for e in entries.values())
    u_count = sum(e["U"]["available"] for e in entries.values())
    both = sum(e["G"]["available"] and e["U"]["available"] for e in entries.values())
    output = {"selector_version": SELECTOR_VERSION, "decision_policy_version": decision["policy_version"],
        **{k: metadata[k] for k in ("snapshot_id", "snapshot_fingerprint", "data_mode", "source_url", "retrieved_at", "metadata_version")},
        "weights": deepcopy(decision["weights"]),
        "relevance": deepcopy(decision["relevance"]),
        "cohort_policy": "highest original S among eligible complete computed scores; exact model ID breaks ties; original cohort rank retained",
        "comparison_cohort": group if order else None, "slots": slots,
        "coverage": {"total_candidate_entries": len(entries), "G_valid": g_count, "task_relevant_U_valid": u_count,
            "complete_G_and_U": both, "numerically_scored": sum(c["S"] is not None for c in candidates.values()),
            "eligibility": {state: sum(e["eligibility"] == state for e in entries.values())
                            for state in ("eligible", "unverified", "ineligible")},
            "candidate_status": {state: sum(e["candidate_status"] == state for e in entries.values())
                                 for state in ("fully_evaluable", "provisional", "unverified", "ineligible")},
            "missing_G": len(entries) - g_count, "missing_U": len(entries) - u_count,
            "index_partition": {"both": both, "G_only": g_count - both, "U_only": u_count - both,
                                "neither": len(entries) - g_count - u_count + both},
            "available_slots": sum(s["status"] == "selected" for s in slots.values()),
            "empty_slot_reasons": {role: s["reason_code"] for role, s in slots.items() if s["status"] == "unavailable"},
            "count_semantics": "Index partition is disjoint; G/U, scores and eligibility overlap and must not be summed."},
        "potential_alternatives": _exploration(coverage, metadata, potential_limit_per_bucket)}
    output["selection_id"] = hashlib.sha256(json.dumps(output, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return output
