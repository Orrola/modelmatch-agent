"""Deterministic recommendation roles and unranked exploration; never compute S."""

import hashlib
import json
from collections import Counter
from copy import deepcopy

from tools.artificial_analysis import numeric
from tools.model_evidence import OPERATIONAL_FIELDS

SELECTOR_VERSION = "decision-oriented-selector-v1"
FAMILY_SCOPE = "Exact-snapshot manually curated AA labels; not provider-verified underlying model equivalence."


def _validate(decision, metadata, coverage):
    for key in ("snapshot_id", "data_mode", "retrieved_at"):
        if decision.get(key) != metadata.get(key) or coverage.get(key) != metadata.get(key):
            raise ValueError("Selector inputs belong to different snapshots or data modes.")
    for key in ("snapshot_fingerprint", "source_url", "metadata_version", "mapping_version"):
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
        if m["mapping_version"] != metadata["mapping_version"] or m["original_name"] != c["name"]:
            raise ValueError("Selector identity metadata does not match the Decision.")
        if (e["eligibility"] != c["eligibility"] or e["candidate_status"] != c["candidate_status"]
                or e["evidence_ids"] != c["evidence_ids"] or e["decision_S"] != c["S"]
                or e["score_blockers"] != c["score_blockers"] or e["constraint_checks"] != c["constraint_checks"]
                or e["decision_score_status"] != c["score_status"]
                or e["decision_score_available"] != (c["S"] is not None)
                or e["verification"]["family"] != m["family_status"]):
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


def _family(meta, binding):
    if meta["family_status"] != "curated_aa_label":
        if meta["family_id"] is not None:
            raise ValueError("An unknown family cannot carry an asserted grouping identity.")
        return None
    source, family = meta["supporting_evidence"], meta["family"]
    identity = {"name": meta["original_name"], "slug": meta["original_slug"],
        "release_date": meta["release_date"], "creator_id": meta["creator_id"], "creator_name": meta["creator_name"]}
    if (not source or not family or not meta["family_id"] or not meta["creator_id"]
            or source["source_model_id"] != meta["model_id"] or source["source_fields"] != identity
            or any(source[k] != binding[k] for k in ("snapshot_id", "data_mode", "source_url", "retrieved_at"))
            or family["creator_id"] != meta["creator_id"] or family["grouping_confidence"] != "curated_aa_label"
            or family["provider_equivalence_status"] != "unknown" or not source["basis"]):
        raise ValueError("Curated family comparison lacks matching snapshot-bound identity support.")
    return meta["family_id"]


def _cost(decision, candidate):
    """Validate existing estimates only; never invent workload, prices or discounts."""
    cost = candidate["estimated_monthly_cost_usd"]
    workload = candidate["workload"]
    keys = ("monthly_requests", "avg_input_tokens", "avg_output_tokens")
    if not numeric(cost) or cost < 0 or any(not numeric(workload.get(k)) or workload[k] < 0 for k in keys):
        return None
    checks = [c for c in candidate["constraint_checks"] if c["metric"] == "monthly_cost_usd"]
    if len(checks) != 1 or not checks[0]["measurement_available"]:
        return None
    if checks[0]["evidence_id"] not in candidate["evidence_ids"]:
        return None
    record = decision["evidence"].get(checks[0]["evidence_id"], {})
    if (record.get("source_type") != "derived" or record.get("evidence_status") != "observed"
            or record.get("metric") != "monthly_cost_usd" or record.get("unit") != "USD/month"
            or record.get("value") != cost or len(record.get("input_evidence_ids", [])) != 2):
        return None
    prices = [decision["evidence"].get(eid, {}) for eid in record["input_evidence_ids"]]
    if not set(record["input_evidence_ids"]) <= set(candidate["evidence_ids"]):
        return None
    expected = {OPERATIONAL_FIELDS[k][0]: OPERATIONAL_FIELDS[k][1] for k in ("input_price", "output_price")}
    if {p.get("metric") for p in prices} != set(expected):
        return None
    for p in [record, *prices]:
        if (p.get("model_id") != candidate["model_id"] or p.get("snapshot_id") != decision["snapshot_id"]
                or p.get("data_mode") != decision["data_mode"] or p.get("evidence_status") != "observed"):
            return None
    if any(p.get("source_type") != "artificial_analysis" or p.get("unit") != expected[p["metric"]]
           or not numeric(p.get("value")) or p["value"] < 0 for p in prices):
        return None
    values = {p["metric"]: p["value"] for p in prices}
    calculated = workload["monthly_requests"] * (
        workload["avg_input_tokens"] * values[OPERATIONAL_FIELDS["input_price"][0]]
        + workload["avg_output_tokens"] * values[OPERATIONAL_FIELDS["output_price"][0]]) / 1_000_000
    if calculated != cost:
        return None
    return {"value": cost, "workload": {k: workload[k] for k in keys}, "currency": "USD",
        "basis": "AA listed input/output token prices per million; no inferred discounts or extra fees",
        "evidence_ids": [record["evidence_id"], *record["input_evidence_ids"]]}


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
                "family_id": metadata["models"][mid]["family_id"],
                "family_status": metadata["models"][mid]["family_status"],
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
    families = {mid: _family(meta, metadata) for mid, meta in sorted(metadata["models"].items())}
    owners = {}
    for mid, family in families.items():
        if family:
            creator = metadata["models"][mid]["creator_id"]
            if family in owners and owners[family] != creator:
                raise ValueError("One curated family cannot belong to different creators.")
            owners[family] = creator
    # Preserve the existing fully-evaluable-first interpretation of split rankings.
    group = "fully_evaluable" if decision["rankings"]["fully_evaluable"] else "provisional"
    ranking = decision["rankings"][group]
    order = [r["model_id"] for r in ranking]
    ranks = {r["model_id"]: {"raw_rank": r["rank"], "raw_position": i} for i, r in enumerate(ranking, 1)}
    candidates = decision["candidates"]

    def selected(mid, reason, **details):
        c = candidates[mid]
        return {"status": "selected", "reason_code": reason, "details": details,
            "candidate": {**{k: deepcopy(c[k]) for k in ("model_id", "name", "G", "U", "O", "S",
                "candidate_status", "eligibility", "evidence_ids", "estimated_monthly_cost_usd")},
                **ranks[mid], "raw_ranking_group": group, "family_id": families[mid],
                "family_status": metadata["models"][mid]["family_status"],
                "family_evidence": deepcopy(metadata["models"][mid]["supporting_evidence"]),
                "creator_id": metadata["models"][mid]["creator_id"],
                "creator_name": metadata["models"][mid]["creator_name"],
                "provider": deepcopy(metadata["models"][mid]["provider"]),
                "provider_status": metadata["models"][mid]["provider_status"]}}

    slots = {"best_overall": _unavailable("no_eligible_scored_candidate"),
             "lower_cost_alternative": _unavailable("best_overall_unavailable"),
             "different_family": _unavailable("best_overall_unavailable")}
    if order:
        best = order[0]
        slots["best_overall"] = selected(best, "highest_original_rank_in_cohort")
        used_families = {families[best]} if families[best] else set()
        used_ids = {best}
        if not families[best]:
            slots["lower_cost_alternative"] = _unavailable("best_overall_family_unknown")
            slots["different_family"] = _unavailable("best_overall_family_unknown")
        else:
            costs = {mid: c for mid in order if (c := _cost(decision, candidates[mid])) is not None}
            if best not in costs:
                slots["lower_cost_alternative"] = _unavailable("best_overall_comparable_cost_unavailable")
            else:
                comparable = [mid for mid in order if mid in costs and costs[mid]["workload"] == costs[best]["workload"]]
                frontier = {mid for mid in comparable if not any(
                    candidates[other]["S"] >= candidates[mid]["S"] and costs[other]["value"] <= costs[mid]["value"]
                    and (candidates[other]["S"] > candidates[mid]["S"] or costs[other]["value"] < costs[mid]["value"])
                    for other in comparable if other != mid)}
                cheaper = [mid for mid in comparable if costs[mid]["value"] < costs[best]["value"]]
                qualifying = [mid for mid in cheaper if mid in frontier and families[mid] and families[mid] not in used_families]
                details = {"comparable_cost_entries": len(comparable), "strictly_lower_cost_entries": len(cheaper),
                    "pareto_entries": len(frontier), "verified_distinct_family_entries": len(qualifying),
                    "pareto_scope": "All comparable scored candidates in the selected cohort, including unknown families."}
                if qualifying:
                    mid = qualifying[0]
                    slots["lower_cost_alternative"] = selected(mid, "highest_original_rank_on_lower_cost_pareto_frontier",
                        **details, cost_comparison=deepcopy(costs[mid]), best_overall_cost=costs[best]["value"])
                    used_families.add(families[mid])
                    used_ids.add(mid)
                else:
                    slots["lower_cost_alternative"] = _unavailable(
                        "no_strictly_lower_comparable_cost" if not cheaper else "no_distinct_curated_family_on_lower_cost_frontier", **details)
            distinct = [mid for mid in order if mid not in used_ids and families[mid] and families[mid] not in used_families]
            creators = {metadata["models"][mid]["creator_id"] for mid in used_ids}
            other_creator = [mid for mid in distinct if metadata["models"][mid]["creator_id"]
                             and metadata["models"][mid]["creator_id"] not in creators]
            if distinct:
                mid = (other_creator or distinct)[0]
                slots["different_family"] = selected(mid, "highest_ranked_distinct_family_with_new_creator"
                    if other_creator else "highest_ranked_distinct_family_same_creator_fallback")
            else:
                slots["different_family"] = _unavailable("no_remaining_distinct_curated_family")
    entries = coverage["models"]
    g_count = sum(e["G"]["available"] for e in entries.values())
    u_count = sum(e["U"]["available"] for e in entries.values())
    both = sum(e["G"]["available"] and e["U"]["available"] for e in entries.values())
    output = {"selector_version": SELECTOR_VERSION, "decision_policy_version": decision["policy_version"],
        **{k: metadata[k] for k in ("snapshot_id", "snapshot_fingerprint", "data_mode", "source_url", "retrieved_at", "metadata_version", "mapping_version")},
        "family_identity_verification_scope": FAMILY_SCOPE, "weights": deepcopy(decision["weights"]),
        "relevance": deepcopy(decision["relevance"]),
        "cohort_policy": "fully_evaluable first; provisional only if no fully_evaluable ranking exists; never mix cohorts",
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
            "verified_family_mappings": sum(f is not None for f in families.values()),
            "unknown_family_entries": sum(f is None for f in families.values()),
            "distinct_curated_families": len({f for f in families.values() if f}),
            "available_slots": sum(s["status"] == "selected" for s in slots.values()),
            "empty_slot_reasons": {role: s["reason_code"] for role, s in slots.items() if s["status"] == "unavailable"},
            "count_semantics": "Index partition is disjoint; G/U, scores, family coverage and eligibility overlap and must not be summed."},
        "potential_alternatives": _exploration(coverage, metadata, potential_limit_per_bucket)}
    output["selection_id"] = hashlib.sha256(json.dumps(output, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return output
