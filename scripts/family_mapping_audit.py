"""Replay retained evidence locally; no model calls, task inference or API refresh."""

import argparse
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from tools.artificial_analysis import numeric
from tools.decision import POLICY_VERSION, decide
from tools.evidence_coverage import analyze_evidence_coverage
from tools.family_mapping import load_family_mapping
from tools.model_evidence import OperationalRequirement, RelevanceDecision, Workload, build_candidates
from tools.model_metadata import build_identity_sidecar
from tools.recommendation_selector import SELECTOR_VERSION, select_recommendations

# These are explicit evidence boundaries, not a replacement for Researcher B.
PROFILES = (
    {"key": "coding", "task_type": "coding_assistant", "domain": None,
     "reason": "No accepted task-specific relevance fixture. Engineering is not verified coding evidence; raw coding index has no established supported mapping.",
     "source": "tests/test_model_evidence.py; docs/round2-reliability-recommendation-audit.md section 3", "fidelity": "unsupported_task_mapping"},
    {"key": "financial", "task_type": "specialized_domain", "domain": "finance",
     "reason": "Retained Finance & Accounting document-analysis audit proxy; not live correctness or investment validation.",
     "source": "scripts/candidate_audit.py finance; tests/test_model_evidence.py", "fidelity": "documented_domain_proxy"},
    {"key": "ecommerce", "task_type": "mixed_or_unknown", "domain": None, "operations": True,
     "reason": "Original stated workload and soft preferences retained. No accepted shopping-specific U mapping or task classification fixture; conservative fallback weight only.",
     "source": "tests/test_recommendation_audit.py workload; local original-input expectations", "fidelity": "unsupported_task_mapping_and_unverified_classification"},
    {"key": "customer_support", "task_type": "tool_agent", "domain": None,
     "reason": "No accepted tool-calling/instruction-following relevance fixture. Strategy & Operations is not verified customer-support evidence.",
     "source": "docs/round2-reliability-recommendation-audit.md section 3; local original-input expectations", "fidelity": "unsupported_task_mapping"},
    {"key": "legal", "task_type": "specialized_domain", "domain": "legal", "context": 100000,
     "reason": "Legal document-analysis proxy with the original 100000-token hard input requirement. Official context limits remain unknown; do not remove the hard constraint.",
     "source": "tests/test_recommendation_audit.py test_unknown_hard_specifications_block_scores_without_excluding_evidence", "fidelity": "domain_proxy_with_original_hard_constraint"},
)
REFERENCES = (
    {"key": "engineering_domain_reference", "task_type": "coding_assistant", "domain": "engineering",
     "reason": "Existing generic engineering-domain audit at coding-default alpha; NOT a verified Coding task mapping.",
     "source": "scripts/candidate_audit.py engineering", "fidelity": "domain_reference_not_task_replay"},
    {"key": "strategy_domain_reference", "task_type": "tool_agent", "domain": "strategy_operations",
     "reason": "Previously retained Strategy & Operations domain audit; NOT a verified Customer Support task mapping.",
     "source": "local round2 snapshot-audit strategy_operations/indices_only", "fidelity": "domain_reference_not_task_replay"},
    {"key": "legal_index_only_reference", "task_type": "specialized_domain", "domain": "legal",
     "reason": "Existing legal index-only diagnostic. NOT the original 100000-token hard-constrained task; no context eligibility is certified.",
     "source": "tests/test_recommendation_audit.py test_selected_legal_index_does_not_require_other_domains_or_diversity", "fidelity": "index_only_reference_not_hard_constrained_task_replay"},
    {"key": "strategy_soft_workload_reference", "task_type": "general_assistant", "domain": "strategy_operations", "operations": True,
     "reason": "Previously retained strategy/workload reference at alpha .70, not an accepted shopping-task relevance decision.",
     "source": "tests/test_recommendation_audit.py; docs/phase6b2-selector-acceptance.md retained Strategy/E-commerce profile", "fidelity": "historical_conditional_profile_not_task_replay"},
)


def prepare_profile(snapshot, profile):
    """Honor existing stated requirements; never synthesize workload for other tasks."""
    requirements = []
    workload = Workload()
    if profile.get("operations"):
        requirements = [OperationalRequirement("monthly_cost_usd", 300), OperationalRequirement("ttft", 2, statistic="mean")]
        workload = Workload(100000, 2000, 500)
    if profile.get("context"):
        requirements.append(OperationalRequirement("context_window", profile["context"], hard=True))
    relevance = RelevanceDecision(profile["key"], profile["domain"], "strong" if profile["domain"] else "none", profile["reason"])
    return build_candidates(snapshot, relevance, requirements, workload=workload, shortlist_size=20)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _selection_summary(selection, metadata, order):
    selected = {role: {"status": slot["status"], "reason": slot["reason_code"],
        "model_id": slot["candidate"]["model_id"] if slot["candidate"] else None,
        "name": slot["candidate"]["name"] if slot["candidate"] else None,
        "S": slot["candidate"]["S"] if slot["candidate"] else None,
        "raw_rank": slot["candidate"]["raw_rank"] if slot["candidate"] else None}
        for role, slot in selection["slots"].items()}
    def coverage(limit):
        ids = [r["model_id"] for r in order[:limit]]
        family = [metadata["models"][mid]["family_id"] for mid in ids]
        known = [f for f in family if f is not None]
        return {"entries": len(ids), "mapped": len(known), "distinct_known_families": len(set(known)),
                "known_configuration_duplicates": len(known) - len(set(known)),
                "unknown": len(ids) - len(known), "unknowns_are_not_deduplicated": True}
    return {"selection_id": selection["selection_id"], "slots": selected,
        "unavailable_slot_count": sum(slot["status"] == "unavailable" for slot in selected.values()),
        "top10_coverage": coverage(10), "top20_coverage": coverage(20)}


def audit(snapshot, before, after):
    """Compare mappings against identical Decisions; never mutate evidence or rankings."""
    frozen = deepcopy(snapshot)
    metadata = [build_identity_sidecar(snapshot, mapping=mapping) for mapping in (before, after)]
    source = {r["id"]: r for page in snapshot["pages"] for r in page["data"]}
    frequencies = {key: {"top10": Counter(), "top20": Counter()} for key in ("primary", "reference")}
    outputs = {"primary": {}, "reference": {}}
    for section, profiles in (("primary", PROFILES), ("reference", REFERENCES)):
        for profile in profiles:
            prepared = prepare_profile(snapshot, profile)
            decision = decide(prepared, task_type=profile["task_type"])
            original = deepcopy(decision)
            group = "fully_evaluable" if decision["rankings"]["fully_evaluable"] else "provisional"
            order = decision["rankings"][group]
            summaries = []
            for sidecar in metadata:
                coverage = analyze_evidence_coverage(snapshot, prepared, sidecar, decision)
                selection = select_recommendations(decision, sidecar, coverage)
                summaries.append(_selection_summary(selection, sidecar, order))
                if decision != original:
                    raise ValueError("Mapping replay changed the raw Decision.")
            for limit in (10, 20):
                frequencies[section][f"top{limit}"].update(r["model_id"] for r in order[:limit])
            rows = []
            for row in order[:20]:
                c, raw = decision["candidates"][row["model_id"]], source[row["model_id"]]
                rows.append({"model_id": c["model_id"], "name": c["name"], "slug": raw.get("slug"),
                    "creator": raw.get("model_creator"), "release_date": raw.get("release_date"), "raw_rank": row["rank"],
                    **{key: deepcopy(c[key]) for key in ("G", "U", "O", "S", "eligibility", "candidate_status", "evidence_ids", "estimated_monthly_cost_usd")}})
            outputs[section][profile["key"]] = {"profile": profile, "weights": decision["weights"],
                "scored_candidates": sum(c["S"] is not None for c in decision["candidates"].values()),
                "counts": decision["counts_before_shortlist"], "index_relevance": decision["relevance"],
                "raw_top20": rows, "raw_decision_digest": _digest(decision), "raw_decision_unchanged": decision == original,
                "before": summaries[0], "after": summaries[1]}
    if snapshot != frozen:
        raise ValueError("Mapping replay changed the source snapshot.")
    priorities = []
    all_ids = set().union(*(set(c) for counts in frequencies.values() for c in counts.values()))
    for mid in sorted(all_ids, key=lambda mid: (-frequencies["primary"]["top10"][mid], -frequencies["primary"]["top20"][mid],
                        -frequencies["reference"]["top10"][mid], -frequencies["reference"]["top20"][mid], mid)):
        raw = source[mid]
        priorities.append({"model_id": mid, "name": raw["name"], "slug": raw.get("slug"),
            "creator": raw.get("model_creator"), "release_date": raw.get("release_date"),
            "primary_top10_appearances": frequencies["primary"]["top10"][mid],
            "primary_top20_appearances": frequencies["primary"]["top20"][mid],
            "reference_top10_appearances": frequencies["reference"]["top10"][mid],
            "reference_top20_appearances": frequencies["reference"]["top20"][mid],
            "after_family_id": metadata[1]["models"][mid]["family_id"],
            "after_family_status": metadata[1]["models"][mid]["family_status"]})
    return {"snapshot_id": snapshot["snapshot_id"], "data_mode": snapshot["data_mode"], "snapshot_fingerprint": metadata[0]["snapshot_fingerprint"],
        "retrieved_at": snapshot.get("retrieved_at"), "source_url": snapshot["source_url"],
        "scope": "Local retained evidence only; references are NOT verified task mappings or production replays.",
        "before_mapping_version": before["version"], "after_mapping_version": after["version"],
        "decision_policy_version": POLICY_VERSION, "selection_policy_version": SELECTOR_VERSION,
        "raw_unmapped_index_coverage": {field: sum(numeric(row.get("evaluations", {}).get(field)) for row in source.values())
            for field in ("artificial_analysis_coding_index", "artificial_analysis_agentic_index")},
        "before_metadata_coverage": metadata[0]["coverage"], "after_metadata_coverage": metadata[1]["coverage"],
        "frequency_semantics": "Exact-ID appearances; primary and reference frequencies are separate. Empty rankings contribute no appearances, not zero benchmark scores.",
        "scenarios": outputs, "priority_candidates": priorities}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(".cache/phase6b4/replay.json"))
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    report = audit(snapshot, load_family_mapping(version="aa-label-families-v1"), load_family_mapping())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": "completed_local_replay", "snapshot_id": report["snapshot_id"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
