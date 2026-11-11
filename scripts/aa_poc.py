"""Run with python -m scripts.aa_poc. Live mode NEVER falls back to mock."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from tools.artificial_analysis import (
    AAError, ArtificialAnalysisClient, FREE_ENDPOINT, audit_snapshot,
    load_mock_snapshot, utc_now,
)

ROOT = Path(__file__).resolve().parents[1]


def cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def report(snapshot: dict, audit: dict) -> str:
    live = snapshot["data_mode"] == "live"
    n = audit["model_count"]
    lines = [
        "# Artificial Analysis Data Access Audit", "",
        f"- Report generated at (UTC): {utc_now()}",
        f"- Data mode: **{'LIVE - real API data' if live else 'MOCK - synthetic protocol data, NOT real evaluations'}**",
        "- Data: [Artificial Analysis](https://artificialanalysis.ai/)",
        f"- Data source: {snapshot['source_url']}",
        f"- Retrieved at (UTC): {snapshot['retrieved_at'] or 'not applicable (mock)'}",
        f"- Snapshot ID: `{snapshot['snapshot_id']}`",
        f"- Cache hit: {snapshot['cache_hit']}; HTTP requests this run: {snapshot['requests_this_run']}",
        f"- Pages: {len(snapshot['pages'])}; complete catalog: {snapshot['complete']}",
        f"- Model count (retrieved snapshot only): **{n}**", "",
        "## Response envelope", "",
        "| Page | Tier | Intelligence Index Version (raw value) | Has more |",
        "|---|---|---|---|",
    ]
    for page in snapshot["pages"]:
        lines.append(f"| {page['pagination']['page']} | {cell(page['tier'])} | {cell(page['intelligence_index_version'])} | {page['pagination']['has_more']} |")
    lines += ["", "## Field coverage and missing values", "",
              "The denominator is the retrieved model count. Numeric means a finite number, not task relevance or score comparability. Zero is not missing.", "",
              "| Metric | Numeric | Null | Absent | Invalid | Missing/invalid rate |",
              "|---|---:|---:|---:|---:|---:|"]
    for label, counts in audit["coverage"].items():
        missing = (n - counts["numeric"]) / n * 100 if n else None
        pct = f"{missing:.1f}%" if missing is not None else "N/A"
        lines.append(f"| {label} | {counts['numeric']} | {counts['null']} | {counts['absent']} | {counts['invalid']} | {pct} |")
    lines += ["", "## Joint coverage", "", "| Field combination | Models with all fields |", "|---|---:|"]
    for label, count in audit["joint_coverage"].items():
        lines.append(f"| {label} | {count} |")
    lines += ["", "## Fixed POC sample (not a capability ranking)", "",
              "Prioritize observed field completeness and rotate creators, up to 20 models. Original AA IDs are join keys; do not guess API model names.", "",
              "| AA model ID | Name | Slug |", "|---|---|---|"]
    for row in audit["candidate_pool"]:
        lines.append(f"| {cell(row['id'])} | {cell(row['name'])} | {cell(row['slug'])} |")
    lines += ["", "## Observed schema (union of paths and types across all retrieved pages)", "", "| Path | Observed types |", "|---|---|"]
    for path, kinds in audit["schema"].items():
        lines.append(f"| `{cell(path)}` | {', '.join(kinds)} |")
    lines += ["", "## Limitations and unverified assumptions", "",
              "- Successful connectivity means an API response was retrieved; a cache hit does not reverify connectivity.",
              "- Pagination is not a server-side atomic snapshot. Version/ID checks cannot guarantee data stayed unchanged during retrieval.",
              "- If pagination is incomplete, coverage applies only to retrieved pages.",
              "- Intelligence Index is not accuracy percent. This audit does not normalize indices or compute decision scores.",
              "- Task relevance, independent Capability Index versions, and underlying benchmark overlap require further review.",
              "- Legacy performance uses medians; performance_v3 uses means. They remain separate without substitution or merging.",
              "- AA documentation schedules legacy performance fields to become null on 2026-12-10; operational policies must identify the metric version.",
              "- TTFT, first-answer-token and end-to-end times are separate; none establishes an enterprise P95 SLA.",
              "- Context, deployment/privacy, provider-specific pricing, cache and reasoning-token costs remain unverified.",
              "- No specialist benchmarks were called, and domain indices are not established as full representations of product scenarios.",
              "- Keep local caches out of source control; confirm redistribution rights before sharing raw responses.",
              "- Assess G/U/operational coverage per use case; this audit alone is not a product-readiness decision.",
              "", "References: [AA API documentation](https://artificialanalysis.ai/data-api/docs); [API Reference](https://artificialanalysis.ai/data-api/docs/reference).", ""]
    return "\n".join(lines)


async def run(args) -> int:
    load_dotenv(ROOT / ".env", override=False)
    if args.mode == "mock":
        output = args.output or ROOT / ".cache/aa/mock-audit.md"
        # An offline test must not overwrite the real-data audit deliverable.
        if output.resolve() in {(ROOT / "docs/aa-data-audit.md").resolve(), (ROOT / ".cache/aa/live-audit.md").resolve()}:
            print("Refusing to overwrite a real-data audit with mock output.")
            return 2
        snapshot = load_mock_snapshot(args.fixture)
    else:
        output = args.output or ROOT / ".cache/aa/live-audit.md"
        client = ArtificialAnalysisClient(cache_dir=ROOT / ".cache/aa", cache_ttl=args.cache_ttl)
        try:
            snapshot = await client.fetch_snapshot(max_pages=args.max_pages, refresh=not args.use_cache)
        except AAError as error:
            print(f"LIVE API not verified: {error}")
            # Preserve previous successful evidence if a later connectivity check fails.
            target = output if not output.exists() else output.with_name(output.stem + "-last-attempt.md")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "# Artificial Analysis Data Access Audit - incomplete\n\n"
                f"- Attempted at (UTC): {utc_now()}\n"
                f"- Data source: {FREE_ENDPOINT}\n"
                "- Data: [Artificial Analysis](https://artificialanalysis.ai/)\n"
                "- Mode: live; no mock fallback.\n"
                f"- Status: **Live API verification failed**. Reason: {error}\n"
                "- No auditable response was retrieved; model counts, schema and coverage remain unverified.\n"
                "- There is no real retrieval timestamp; no benchmark values are supplied.\n", encoding="utf-8",
            )
            print(f"Failure report saved: {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}")
            return 1
    audit = audit_snapshot(snapshot)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report(snapshot, audit), encoding="utf-8")
    # Machine-readable metadata enables reproducible follow-on work; ignored cache only.
    metadata = ROOT / ".cache/aa" / ("live-audit.json" if args.mode == "live" else "mock-audit.json")
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Mode: {snapshot['data_mode']}; models: {audit['model_count']}; pages: {len(snapshot['pages'])}; complete catalog: {snapshot['complete']}; cache hit: {snapshot['cache_hit']}")
    print(f"Report: {output}")
    if not snapshot["complete"]:
        print("Catalog incomplete: this report covers retrieved pages only. Increase --max-pages to fetch more.")
    return 0 if snapshot["complete"] and audit["model_count"] > 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("live", "mock"), default="live")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--use-cache", action="store_true", help="Allow a fresh local cache; default always checks live connectivity.")
    parser.add_argument("--cache-ttl", type=float, default=3600)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/fixtures/aa_free_mock.json")
    parser.add_argument("--output", type=Path)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
