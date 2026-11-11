"""Replay one existing AA snapshot offline; never refresh or call any API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.artificial_analysis import utc_now
from tools.model_evidence import OperationalRequirement, RelevanceDecision, build_candidates

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    ("finance", "Financial document analysis", "Finance & Accounting is the selected proxy for financial document analysis; does not establish tool-use or document-length coverage."),
    ("engineering", "Engineering technical analysis", "Engineering is the selected domain proxy; the particular engineering task still requires relevance review."),
    ("healthcare", "Medical information analysis", "Healthcare & Medical is the selected domain proxy; this is not clinical validation or approval for medical use."),
    (None, "Creative marketing", "No task-equivalent AA domain index has been established for this audit."),
)


def audit(snapshot: dict, *, shortlist_size: int = 20) -> tuple[str, dict]:
    lines = [
        "# Phase 2A - Domain Candidates and Evidence Audit", "",
        f"- Generated at (UTC): {utc_now()}",
        f"- Snapshot: `{snapshot['snapshot_id']}`; mode: **{snapshot['data_mode']}**",
        f"- Original retrieval time: {snapshot.get('retrieved_at')}; no network access or snapshot refresh in this run.",
        "- Data: [Artificial Analysis](https://artificialanalysis.ai/)",
        "- Count all models in the shared snapshot before shortlisting; do not require all six domain indices.",
        "- Scenario mappings are explicit audit assumptions, not automatically inferred or empirically validated task relevance.",
        "- Profiles: index_only has no operational requirements; operations requires input/output prices, v3 mean TTFT and mean output speed, without hard targets.",
        "- With no operational requirements, C-valid means no operational fields were requested, not complete operational specifications.",
        "", "| Domain / Profile | Total | A-valid | B-valid | C-valid | Fully evaluable | Provisional | Ineligible | Unverified |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    results = {}
    for domain, use_case, rationale in SCENARIOS:
        decision = RelevanceDecision(use_case, domain, "strong" if domain else "none", rationale)
        for profile in ("index_only", "operations"):
            requirements = () if profile == "index_only" else tuple(
                OperationalRequirement(metric) for metric in ("input_price", "output_price", "ttft", "output_speed"))
            result = build_candidates(snapshot, decision, requirements, shortlist_size=shortlist_size)
            key = f"{domain or 'unsupported'}-{profile}"
            results[key] = result
            c = result["counts_before_shortlist"]
            lines.append(f"| {key} | {c['total']} | {c['A_valid']} | {c['B_valid']} | {c['C_valid']} | {c['fully_evaluable']} | {c['provisional']} | {c['ineligible']} | {c['unverified']} |")
    lines += ["", "## Interpretation and boundaries", "",
              f"- Shortlist limit per status: {shortlist_size}; complete evidence and missing manifests are saved under ignored `.cache/aa/phase2a/`.",
              "- Retrieval prioritizes selected-domain U, then G, and rotates creators; this is not final decision scoring.",
              "- fully_evaluable means fields are evaluable under the stated mapping/requirements, not production, SLA or procurement readiness.",
              "- Missing soft evidence is provisional; unknown hard constraints are unverified; known hard violations are ineligible.",
              "- These profiles have no hard constraints; zero ineligible/unverified counts do not verify deployment conditions.",
              "- Partial relevance remains provisional even with numeric U; unsupported tasks get no invented U.",
              "- Independent Capability Index versions are unavailable in this snapshot; keep null instead of borrowing the Intelligence Index version.",
              "- Read performance_v3 means only; never fall back to legacy medians or use means to establish a P95 SLA.",
              "- Replay uses historical data, not fresh connectivity verification; pagination is not an atomic server snapshot.",
              "- Context, deployment and residency await future Gemini Search Grounding and official-page verification; they remain unknown.",
              "- This audit only prepares evidence. The separate decision engine computes penalties, scores and sensitivity; see README.md.", ""]
    return "\n".join(lines), results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / ".cache/aa/aa-free-snapshot.json")
    parser.add_argument("--shortlist-size", type=int, default=20)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/aa/phase2a-data-audit.md")
    args = parser.parse_args()
    if not args.snapshot.is_file():
        print("Snapshot missing; no API call or mock fallback. Run the Phase 1 POC first.")
        return 1
    snapshot = json.loads(args.snapshot.read_text())
    if snapshot.get("data_mode") != "live" and args.output.resolve().is_relative_to((ROOT / "docs").resolve()):
        print("Refusing to write a mock candidate audit to internal acceptance documents.")
        return 2
    text, results = audit(snapshot, shortlist_size=args.shortlist_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    cache = ROOT / ".cache/aa/phase2a"
    cache.mkdir(parents=True, exist_ok=True)
    for key, result in results.items():
        (cache / f"{key}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        (cache / f"{key}-missing-manifest.json").write_text(
            json.dumps({"snapshot_id": result["snapshot_id"], "data_mode": result["data_mode"],
                        "missing_manifest": result["missing_manifest"]},
                       ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(key, result["counts_before_shortlist"])
    print("Audit report: ", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
