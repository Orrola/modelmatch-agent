"""Grounded Writer contract and deterministic report rendering.

The Writer selects canonical content, not arbitrary prose or numeric claims.
This prevents fabricated benchmark values and preserves the Decision Tool order.
"""

from modelmatch_schemas import WriterOutput

VALIDATION_TEXT = {
    "task_pilot": "Run a pilot on representative internal tasks and evaluate factual reliability.",
    "tool_use_pilot": "Test tool selection, argument correctness and recovery on real workflows.",
    "verify_context": "Verify exact model-version input/output limits using official documentation.",
    "verify_deployment": "Verify deployment, privacy and data-residency requirements with official sources.",
    "measure_workload": "Measure workload-specific token usage, cost, mean latency and tail latency.",
    "check_index_versions": "Verify benchmark relevance, independent index versions and data freshness.",
}


def writer_payload(decision):
    ranking = decision["rankings"]["fully_evaluable"]
    status = "supported"
    if not ranking:
        ranking = decision["rankings"]["provisional"]
        status = "provisional" if ranking else "not_supported"
    if not decision["catalog_complete"] and ranking:
        status = "provisional"
    ids = [r["model_id"] for r in ranking[:3]]
    evidence_ids = sorted({eid for mid in ids for eid in decision["candidates"][mid]["evidence_ids"]
                           if decision["evidence"][eid]["evidence_status"] == "observed"})
    return {"status": status, "candidate_ids": ids, "evidence_ids": evidence_ids,
            "candidates": [decision["candidates"][mid] for mid in ids],
            "evidence": [decision["evidence"][eid] for eid in evidence_ids],
            "weights": decision["weights"], "assumptions": decision["assumptions"]}


def validate_writer(intent: WriterOutput, payload):
    if intent.candidate_ids != payload["candidate_ids"]:
        raise ValueError("Writer cannot change candidate IDs or ranking order.")
    if set(intent.evidence_ids) != set(payload["evidence_ids"]):
        raise ValueError("Writer must preserve the canonical source references.")
    if not intent.validation_steps:
        raise ValueError("Writer must request further validation.")


def _text(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("[", "\\[").replace("]", "\\]").replace("<", "&lt;").replace(">", "&gt;")


def render_recommendation(decision, intent: WriterOutput):
    payload = writer_payload(decision)
    validate_writer(intent, payload)
    weights = decision["weights"]
    lines = ["# ModelMatch AI Recommendation", "", f"Conclusion status: **{payload['status']}**.", "",
             "This is a conditional shortlist under the supplied requirements and available evidence, not a guarantee of production suitability.",
             f"Task type: `{weights['task_type']}`. General weight: {weights['alpha']}; source: `{weights['source']}`.", "",
             "Data: [Artificial Analysis](https://artificialanalysis.ai/).",
             f"Snapshot: `{decision['snapshot_id']}`; retrieved: {_text(decision['retrieved_at'])}; data mode: `{decision['data_mode']}`.", ""]
    if decision["data_mode"] == "mock":
        lines += ["**Offline synthetic test output. Not real model evaluations or a procurement recommendation.**", ""]
    if intent.candidate_ids:
        lines += ["## " + ("Provisional shortlist" if payload["status"] == "provisional" else "Top candidates (up to three)"), "",
                  "G and U are original index points. O and S are custom policy points, not accuracy percentages or an official AA benchmark.", "",
                  "| Model | G | U | O | S | Candidate status | Eligibility |", "|---|---:|---:|---:|---:|---|---|"]
        for mid in intent.candidate_ids:
            c = decision["candidates"][mid]
            lines.append(f"| {_text(c['name'])} (`{mid}`) | {c['G']} | {c['U']} | {c['O']} | {c['S']} | {c['candidate_status']} | {c['eligibility']} |")
        lines += ["", "## Tradeoffs and operational adjustments", ""]
        for mid in intent.candidate_ids:
            c = decision["candidates"][mid]
            parts = [f"{name}: {item['deduction']} ({item['status']})" for name, item in c["operational_penalties"].items()]
            lines.append(f"- {_text(c['name'])}: " + "; ".join(parts) + ". Review G versus the selected task-relevant U before piloting.")
    else:
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
    lines += ["", "## Weight sensitivity", "",
              "The same evidence and penalties were reused at alpha values: " + ", ".join(str(s["alpha"]) for s in decision["sensitivity"]) + ". Full rank changes are returned in the structured decision.",
              "", "## Next validation steps", ""]
    lines += [f"- {VALIDATION_TEXT[step]}" for step in dict.fromkeys(intent.validation_steps)]
    return "\n".join(lines) + "\n"
