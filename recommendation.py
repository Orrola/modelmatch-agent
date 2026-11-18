"""Grounded Writer contract and deterministic report rendering.

The Writer selects canonical content, not arbitrary prose or numeric claims.
This prevents fabricated benchmark values and preserves the Decision Tool order.
"""

import hashlib
import json

from modelmatch_schemas import WriterOutput

_LEGACY_SELECTION = object()
ROLE_ORDER = ("best_overall", "lower_cost_alternative", "different_family")

VALIDATION_TEXT = {
    "task_pilot": "Run a pilot on representative internal tasks and evaluate factual reliability.",
    "tool_use_pilot": "Test tool selection, argument correctness and recovery on real workflows.",
    "verify_context": "Verify exact model-version input/output limits using official documentation.",
    "verify_deployment": "Verify deployment, privacy and data-residency requirements with official sources.",
    "measure_workload": "Measure workload-specific token usage, cost, mean latency and tail latency.",
    "check_index_versions": "Verify benchmark relevance, independent index versions and data freshness.",
}


def writer_payload(decision, selection=_LEGACY_SELECTION):
    ranking = decision["rankings"]["fully_evaluable"]
    status = "supported"
    if not ranking:
        ranking = decision["rankings"]["provisional"]
        status = "provisional" if ranking else "not_supported"
    if not decision["catalog_complete"] and ranking:
        status = "provisional"
    ids = [r["model_id"] for r in ranking[:3]]
    roles = []
    basis = "legacy_raw_ranking"
    if selection is not _LEGACY_SELECTION:
        basis = "selector_unavailable" if selection is None else "canonical_selection"
        ids = []
        if selection is not None:
            signed = {k: v for k, v in selection.items() if k != "selection_id"}
            fingerprint = hashlib.sha256(json.dumps(signed, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if (fingerprint != selection["selection_id"] or selection["snapshot_id"] != decision["snapshot_id"]
                    or selection["data_mode"] != decision["data_mode"] or selection["weights"] != decision["weights"]
                    or selection["decision_policy_version"] != decision["policy_version"]
                    or set(selection["slots"]) != set(ROLE_ORDER)):
                raise ValueError("Canonical selection does not match this Decision.")
            for role in ROLE_ORDER:
                slot = selection["slots"][role]
                if slot["status"] == "unavailable":
                    if slot["candidate"] is not None:
                        raise ValueError("An unavailable recommendation slot cannot contain a candidate.")
                    continue
                if slot["status"] != "selected":
                    raise ValueError("Canonical recommendation slot status is invalid.")
                supplied = slot["candidate"]
                candidate = decision["candidates"].get(supplied["model_id"])
                if (candidate is None or candidate["eligibility"] != "eligible" or candidate["S"] is None
                        or any(supplied[k] != candidate[k] for k in ("G", "U", "O", "S", "evidence_ids", "candidate_status"))
                        or supplied["model_id"] in ids):
                    raise ValueError("Canonical candidate does not match scored Decision evidence.")
                ids.append(supplied["model_id"])
                roles.append({"role": role, "model_id": supplied["model_id"], "raw_rank": supplied["raw_rank"],
                              "reason_code": slot["reason_code"]})
        status = "not_supported" if not ids else "provisional" if not decision["catalog_complete"] or any(
            decision["candidates"][mid]["candidate_status"] != "fully_evaluable" for mid in ids) else "supported"
    evidence_ids = sorted({eid for mid in ids for eid in decision["candidates"][mid]["evidence_ids"]
                           if decision["evidence"][eid]["evidence_status"] == "observed"})
    return {"status": status, "candidate_ids": ids, "evidence_ids": evidence_ids,
            "candidates": [decision["candidates"][mid] for mid in ids],
            "evidence": [decision["evidence"][eid] for eid in evidence_ids],
            "weights": decision["weights"], "assumptions": decision["assumptions"], "recommendation_basis": basis,
            "selection_id": selection["selection_id"] if basis == "canonical_selection" else None,
            "selection_roles": roles}


class WriterValidationError(ValueError):
    """A stable rule identifier without model-generated text."""

    def __init__(self, code, message):
        self.validation_code = code
        super().__init__(message)


def validate_writer(intent: WriterOutput, payload):
    if intent.candidate_ids != payload["candidate_ids"]:
        raise WriterValidationError("candidate_order_mismatch", "Writer cannot change candidate IDs or ranking order.")
    if set(intent.evidence_ids) != set(payload["evidence_ids"]):
        raise WriterValidationError("evidence_set_mismatch", "Writer must preserve the canonical source references.")
    if not intent.validation_steps:
        raise WriterValidationError("validation_steps_missing", "Writer must request further validation.")


def _text(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("[", "\\[").replace("]", "\\]").replace("<", "&lt;").replace(">", "&gt;")


def render_recommendation(decision, intent: WriterOutput, selection=_LEGACY_SELECTION):
    payload = writer_payload(decision, selection)
    validate_writer(intent, payload)
    weights = decision["weights"]
    lines = ["# ModelMatch AI Recommendation", "", f"Conclusion status: **{payload['status']}**.", "",
             "This is a conditional shortlist under the supplied requirements and available evidence, not a guarantee of production suitability.",
             f"Task type: `{weights['task_type']}`. General weight: {weights['alpha']}; source: `{weights['source']}`.", "",
             "Data: [Artificial Analysis](https://artificialanalysis.ai/).",
             f"Snapshot: `{decision['snapshot_id']}`; retrieved: {_text(decision['retrieved_at'])}; data mode: `{decision['data_mode']}`.", ""]
    if decision["data_mode"] == "mock":
        lines += ["**Offline synthetic test output. Not real model evaluations or a procurement recommendation.**", ""]
    if payload["recommendation_basis"] == "selector_unavailable":
        lines += ["**Selector unavailable. This is a deterministic fallback, not a verified decision-oriented recommendation.**",
                  "The original Decision, raw rankings and evidence remain available in the API result. No Writer generation was performed.", ""]
    elif payload["recommendation_basis"] == "canonical_selection":
        lines += [f"Canonical selection: `{payload['selection_id']}`. Roles are not Raw Ranking positions.",
                  "Family comparison uses snapshot-bound curated AA labels, not verified underlying model equivalence.", ""]
    if intent.candidate_ids:
        lines += ["## " + ("Provisional shortlist" if payload["status"] == "provisional" else "Top candidates (up to three)"), "",
                  "G and U are original index points. O and S are custom policy points, not accuracy percentages or an official AA benchmark.", "",
                  "| Model | G | U | O | S | Candidate status | Eligibility |", "|---|---:|---:|---:|---:|---|---|"]
        for mid in intent.candidate_ids:
            c = decision["candidates"][mid]
            lines.append(f"| {_text(c['name'])} (`{mid}`) | {c['G']} | {c['U']} | {c['O']} | {c['S']} | {c['candidate_status']} | {c['eligibility']} |")
        for role in payload["selection_roles"]:
            lines.append(f"- {role['role']}: `{role['model_id']}`; original rank {role['raw_rank']}; {role['reason_code']}.")
        lines += ["", "## Tradeoffs and operational adjustments", ""]
        for mid in intent.candidate_ids:
            c = decision["candidates"][mid]
            parts = [f"{name}: {item['deduction']} ({item['status']})" for name, item in c["operational_penalties"].items()]
            lines.append(f"- {_text(c['name'])}: " + "; ".join(parts) + ". Review G versus the selected task-relevant U before piloting.")
    elif payload["recommendation_basis"] != "selector_unavailable":
        lines += ["No reliable numeric recommendation is supported. Missing G/U, requested operational evidence or hard-constraint verification must be resolved first.", ""]
    lines += ["", "## Evidence and sources", ""]
    if not intent.evidence_ids:
        lines.append("No ranked candidate has a complete set of supporting evidence. The returned missing manifest retains the unresolved fields.")
    for eid in intent.evidence_ids:
        e = decision["evidence"][eid]
        source = f"[source]({e['source_url']})" if e["source_url"] else "source unverified"
        lines.append(f"- `{eid}`: model `{e['model_id']}`, `{e['metric']}` = {_text(e['value'])} {_text(e['unit'])}; statistic={e['statistic']}; index version={e['index_version']}; source type={e['source_type']}; input evidence={_text(', '.join(e.get('input_evidence_ids', ()))) or 'none'}; {source}; retrieved {_text(e['retrieved_at'])}.")
    lines += ["", "## Limitations and missing evidence", "",
              f"Task-index match: `{decision['relevance']['match_status']}`. {_text(decision['relevance']['rationale'])}", ""]
    for status in ("fully_evaluable", "provisional", "ineligible", "unverified"):
        count = sum(c["candidate_status"] == status for c in decision["candidates"].values())
        lines.append(f"- {status}: {count} candidates; categories are kept separate.")
    reasons = sorted({f["reason"] for m in decision["missing_manifest"] for f in m["missing_fields"] if f["required"]})
    lines += [f"- Required evidence gaps: {', '.join(reasons) if reasons else 'none recorded for the current requirements'}."]
    lines += [f"- {a}" for a in decision["assumptions"]]
    if payload["recommendation_basis"] == "canonical_selection":
        lines += ["- Potential Alternatives remain separate, unranked and unscored; they are not Writer recommendation candidates."]
        lines += [f"- Unavailable {role}: {selection['slots'][role]['reason_code']}." for role in ROLE_ORDER
                  if selection["slots"][role]["status"] == "unavailable"]
    lines += ["", "## Weight sensitivity", "",
              "The same evidence and penalties were reused at alpha values: " + ", ".join(str(s["alpha"]) for s in decision["sensitivity"]) + ". Full rank changes are returned in the structured decision.",
              "", "## Next validation steps", ""]
    lines += [f"- {VALIDATION_TEXT[step]}" for step in dict.fromkeys(intent.validation_steps)]
    return "\n".join(lines) + "\n"
