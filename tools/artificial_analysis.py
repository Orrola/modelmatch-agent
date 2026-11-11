"""AA Free API access. No agents, scoring, or implicit mock fallback.

Cache entries contain API data, never authentication headers. Treat snapshots as
local data until redistribution rights have been checked.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

FREE_ENDPOINT = "https://artificialanalysis.ai/api/v2/language/models/free"
GENERAL = "artificial_analysis_intelligence_index"
CAPABILITIES = (
    "artificial_analysis_finance_and_accounting_index",
    "artificial_analysis_strategy_and_ops_index",
    "artificial_analysis_legal_index",
    "artificial_analysis_healthcare_and_medical_index",
    "artificial_analysis_engineering_index",
    "artificial_analysis_economics_index",
)
METRICS = {
    "General Intelligence": f"evaluations.{GENERAL}",
    **{key.removeprefix("artificial_analysis_"): f"evaluations.{key}" for key in CAPABILITIES},
    "Input price (USD / 1M tokens)": "pricing.price_1m_input_tokens",
    "Output price (USD / 1M tokens)": "pricing.price_1m_output_tokens",
    "Legacy output speed (median tokens/s)": "performance.median_output_tokens_per_second",
    "Legacy TTFT (median seconds)": "performance.median_time_to_first_token_seconds",
    "Legacy first answer token (median seconds)": "performance.median_time_to_first_answer_token_seconds",
    "Legacy end-to-end latency (median seconds)": "performance.median_end_to_end_response_time_seconds",
    "v3 output speed (mean tokens/s)": "performance_v3.mean_output_tokens_per_second",
    "v3 TTFT (mean seconds)": "performance_v3.mean_time_to_first_token_seconds",
    "v3 first answer token (mean seconds)": "performance_v3.mean_time_to_first_answer_token_seconds",
}
MISSING = object()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AAError(RuntimeError):
    """Safe error: never contains request headers or raw response bodies."""


def validate_page(body: Any, expected_page: int) -> None:
    if not isinstance(body, dict):
        raise AAError("AA schema error: response must be an object.")
    if not isinstance(body.get("tier"), str):
        raise AAError("AA schema error: tier must be a string.")
    version = body.get("intelligence_index_version")
    if isinstance(version, bool) or not isinstance(version, (int, float, str)):
        raise AAError("AA schema error: missing/invalid Intelligence Index version.")
    pagination = body.get("pagination")
    if not isinstance(pagination, dict):
        raise AAError("AA schema error: missing pagination object.")
    if type(pagination.get("page")) is not int or pagination["page"] != expected_page:
        raise AAError("AA schema error: unexpected page number.")
    if type(pagination.get("has_more")) is not bool:
        raise AAError("AA schema error: has_more must be boolean.")
    if not isinstance(body.get("data"), list):
        raise AAError("AA schema error: data must be an array.")
    if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] for row in body["data"]):
        raise AAError("AA schema error: every model needs a nonempty string id.")


class ArtificialAnalysisClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        cache_dir: Path | None = None,
        cache_ttl: float = 3600,
        timeout: float = 30,
        max_retries: int = 2,
        max_retry_wait: float = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._api_key = api_key if api_key is not None else os.getenv("AA_API_KEY", "")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_retry_wait = max_retry_wait
        self.transport = transport
        if timeout <= 0 or cache_ttl < 0 or max_retries < 0 or max_retry_wait < 0:
            raise AAError("Timeout must be positive; TTL and retry limits must be nonnegative.")

    def _read_cache(self, max_pages: int) -> dict | None:
        if self.cache_dir is None:
            return None
        try:
            snapshot = json.loads((self.cache_dir / "aa-free-snapshot.json").read_text())
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(snapshot["retrieved_at"])).total_seconds()
            pages = snapshot["pages"]
            if not 0 <= age < self.cache_ttl or not pages or len(pages) > max_pages:
                return None
            if snapshot["source_url"] != FREE_ENDPOINT or snapshot["data_mode"] != "live":
                return None
            for number, page in enumerate(pages, 1):
                validate_page(page, number)
            if any(not page["pagination"]["has_more"] for page in pages[:-1]):
                return None
            if pages[-1]["pagination"]["has_more"] and len(pages) < max_pages:
                return None  # A one-page probe must not prevent a later full fetch.
            if any((page["intelligence_index_version"], page["tier"]) !=
                   (pages[0]["intelligence_index_version"], pages[0]["tier"]) for page in pages):
                return None
            ids = [row["id"] for page in pages for row in page["data"]]
            if len(ids) != len(set(ids)):
                return None
            snapshot["complete"] = not pages[-1]["pagination"]["has_more"]
            snapshot["cache_hit"] = True
            snapshot["requests_this_run"] = 0
            return snapshot
        except (OSError, ValueError, KeyError, TypeError, AAError):
            return None

    def _write_cache(self, snapshot: dict) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Atomic replacement avoids exposing a half-written snapshot to another run.
        fd, name = tempfile.mkstemp(prefix="aa-", suffix=".tmp", dir=self.cache_dir)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(snapshot, stream, ensure_ascii=False, allow_nan=False)
            Path(name).replace(self.cache_dir / "aa-free-snapshot.json")
        finally:
            Path(name).unlink(missing_ok=True)

    async def fetch_snapshot(self, *, max_pages: int = 10, refresh: bool = False) -> dict:
        if max_pages < 1:
            raise AAError("max_pages must be at least 1.")
        if not refresh:
            cached = self._read_cache(max_pages)
            if cached is not None:
                return cached
        if not self._api_key.strip():
            raise AAError("AA_API_KEY is missing. Configure local .env; no live request was made.")
        pages, rate_limits = [], []
        requests = 0
        started_at = utc_now()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout), transport=self.transport,
            follow_redirects=False, headers={"x-api-key": self._api_key, "Accept": "application/json"},
        ) as client:
            for number in range(1, max_pages + 1):
                for attempt in range(self.max_retries + 1):
                    requests += 1
                    try:
                        response = await client.get(FREE_ENDPOINT, params={"page": number})
                    except httpx.RequestError:
                        if attempt >= self.max_retries:
                            raise AAError("AA network/timeout failure after bounded retries.") from None
                        await asyncio.sleep(min(2 ** attempt, self.max_retry_wait))
                        continue
                    status = response.status_code
                    if status == 429 or status >= 500:
                        raw_wait = response.headers.get("Retry-After")
                        try:
                            wait = float(raw_wait) if raw_wait is not None else float(2 ** attempt)
                        except ValueError:
                            wait = float("inf")  # Unknown date format: do not retry prematurely.
                        if not math.isfinite(wait) or wait < 0 or wait > self.max_retry_wait:
                            raise AAError(f"AA HTTP {status}: retry delay exceeds local wait budget; retry later.")
                        if attempt >= self.max_retries:
                            raise AAError(f"AA HTTP {status}: bounded retries exhausted.")
                        await asyncio.sleep(wait)
                        continue
                    if status != 200:
                        raise AAError(f"AA HTTP {status}: live request failed; no mock fallback.")
                    try:
                        body = response.json()
                    except ValueError:
                        raise AAError("AA returned invalid JSON.") from None
                    validate_page(body, number)
                    if pages and (body["intelligence_index_version"] != pages[0]["intelligence_index_version"] or body["tier"] != pages[0]["tier"]):
                        raise AAError("AA tier/index version changed during pagination; snapshot rejected.")
                    pages.append(body)
                    rate_limits.append({name: response.headers[name] for name in (
                        "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"
                    ) if name in response.headers})
                    break
                if not pages[-1]["pagination"]["has_more"]:
                    break
        ids = [row["id"] for page in pages for row in page["data"]]
        if len(ids) != len(set(ids)):
            raise AAError("AA pagination returned duplicate model IDs; snapshot rejected.")
        digest = hashlib.sha256(json.dumps(pages, sort_keys=True).encode()).hexdigest()[:16]
        snapshot = {
            "source_url": FREE_ENDPOINT, "data_mode": "live", "started_at": started_at,
            "retrieved_at": utc_now(), "snapshot_id": digest, "pages": pages,
            "complete": not pages[-1]["pagination"]["has_more"], "cache_hit": False,
            "requests_this_run": requests, "rate_limits": rate_limits,
        }
        self._write_cache(snapshot)
        return snapshot


def load_mock_snapshot(path: Path) -> dict:
    """Explicit offline-only fixtures; never called as a live error fallback."""
    fixture = json.loads(path.read_text())
    if fixture.get("fixture_kind") != "synthetic_protocol_test_only":
        raise AAError("Fixture must be explicitly labeled synthetic_protocol_test_only.")
    pages = copy.deepcopy(fixture["pages"])
    for number, page in enumerate(pages, 1):
        validate_page(page, number)
    if not pages:
        raise AAError("Mock fixture has no pages.")
    return {
        "data_mode": "mock", "source_url": "offline synthetic fixture (NOT real evaluations)",
        "retrieved_at": None, "snapshot_id": "mock-protocol-only", "pages": pages,
        "complete": not pages[-1]["pagination"]["has_more"], "cache_hit": False,
        "requests_this_run": 0, "rate_limits": [],
    }


def get_path(row: dict, path: str) -> Any:
    value: Any = row
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def numeric(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def schema_inventory(value: Any, path: str = "$", result: dict | None = None) -> dict:
    """Union of observed paths/types over ALL rows/pages, not just the first model."""
    result = {} if result is None else result
    kind = "null" if value is None else type(value).__name__
    result.setdefault(path, set()).add(kind)
    if isinstance(value, dict):
        for key, child in value.items():
            schema_inventory(child, f"{path}.{key}", result)
    elif isinstance(value, list):
        for child in value:
            schema_inventory(child, f"{path}[]", result)
    return result


def audit_snapshot(snapshot: dict) -> dict:
    rows = [row for page in snapshot["pages"] for row in page["data"]]
    coverage = {}
    for label, path in METRICS.items():
        counts = {"numeric": 0, "null": 0, "absent": 0, "invalid": 0}
        for row in rows:
            value = get_path(row, path)
            category = "absent" if value is MISSING else "null" if value is None else "numeric" if numeric(value) else "invalid"
            counts[category] += 1
        coverage[label] = {"path": path, **counts}
    inventory: dict = {}
    for page in snapshot["pages"]:
        schema_inventory(page, result=inventory)
    quality_paths = [f"evaluations.{key}" for key in (GENERAL, *CAPABILITIES)]
    price_paths = ["pricing.price_1m_input_tokens", "pricing.price_1m_output_tokens"]
    joint = {}
    for family, paths in {
        "G + all six U": quality_paths,
        "G + all six U + input/output prices": quality_paths + price_paths,
        "G + all six U + prices + legacy speed/TTFT": quality_paths + price_paths + [METRICS["Legacy output speed (median tokens/s)"], METRICS["Legacy TTFT (median seconds)"]],
        "G + all six U + prices + v3 speed/TTFT": quality_paths + price_paths + [METRICS["v3 output speed (mean tokens/s)"], METRICS["v3 TTFT (mean seconds)"]],
    }.items():
        joint[family] = sum(all(numeric(get_path(row, path)) for path in paths) for row in rows)
    # Deterministic audit pool, NOT a quality ranking; prefer data completeness,
    # then round-robin creators. Persist the IDs in the report for replay.
    by_creator: dict[str, list] = {}
    for row in sorted(rows, key=lambda r: (-sum(numeric(get_path(r, p)) for p in METRICS.values()), r["id"])):
        creator = row.get("model_creator") or {}
        creator_id = str(creator.get("id", "unknown")) if isinstance(creator, dict) else "unknown"
        by_creator.setdefault(creator_id, []).append(row)
    candidates = []
    while by_creator and len(candidates) < 20:
        for creator in list(by_creator):
            row = by_creator[creator].pop(0)
            candidates.append({"id": row["id"], "name": row.get("name"), "slug": row.get("slug")})
            if not by_creator[creator]:
                del by_creator[creator]
            if len(candidates) == 20:
                break
    return {"model_count": len(rows), "coverage": coverage, "joint_coverage": joint,
            "schema": {key: sorted(types) for key, types in sorted(inventory.items())},
            "candidate_pool": candidates}
