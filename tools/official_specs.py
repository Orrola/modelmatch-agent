"""Separate Vertex Search Grounding with conservative official-source verification.

Grounding never supplies benchmark indices. A generated claim is not verified
until a cited official page, literal excerpt, exact version and fresh date agree.
"""

from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from tools.artificial_analysis import utc_now
from vertex_runtime import CallBudget, VertexConfig, safe_error

OFFICIAL_DOMAINS = {
    "google": ("ai.google.dev", "cloud.google.com", "docs.cloud.google.com"),
    "openai": ("developers.openai.com", "platform.openai.com", "openai.com"),
    "anthropic": ("docs.anthropic.com", "platform.claude.com", "docs.claude.com", "anthropic.com"),
}
SPEC_METRICS = {"context_window", "max_input_tokens", "max_output_tokens", "deployment", "data_residency"}
LABELS = {
    "context_window": r"context[ _-]*(?:window|length|limit)",
    "max_input_tokens": r"(?:max(?:imum)?[ _-]*input|input[ _-]*(?:tokens|limit))",
    "max_output_tokens": r"(?:max(?:imum)?[ _-]*output|output[ _-]*(?:tokens|limit))",
    "deployment": r"deploy|hosted|on-prem",
    "data_residency": r"residency|region|location",
}


def normalized(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass(frozen=True)
class SpecRequest:
    model_id: str
    model_name: str
    model_slug: str
    provider: str
    snapshot_id: str
    metrics: tuple[str, ...]


@dataclass(frozen=True)
class SpecEvidence:
    model_id: str
    snapshot_id: str
    metric: str
    value: int | str | None = None
    exact_version: str | None = None
    source_url: str | None = None
    excerpt: str | None = None
    retrieved_at: str = field(default_factory=utc_now)
    source_date: str | None = None
    verification_status: str = "unknown"
    reason: str = "not_verified"
    verification_mode: str = "live"


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "tr", "div", "li", "h1", "h2", "h3"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def whitespace(text):
    return " ".join(text.split())


def official_url(url, domains):
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.hostname in domains and parsed.port in (None, 443) and not parsed.username and not parsed.password
    except ValueError:
        return False


def public_diagnostics(value):
    """Retain provider diagnostics without authentication fields or bearer secrets."""
    if isinstance(value, dict):
        return {k: public_diagnostics(v) for k, v in value.items()
                if k.casefold() not in {"authorization", "api_key", "access_token", "refresh_token", "client_secret", "headers"}}
    if isinstance(value, list):
        return [public_diagnostics(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"(?i)bearer\s+[^\s\"'<>]+|AIza[\w-]+", "[REDACTED]", value)
    return value


def discovery_prompt(request, domains, metrics):
    """Discover cited claims; Python remains responsible for verification."""
    return (
        "Use one focused Google Search query to find official documentation for this exact model and requested specifications. "
        f"Prefer {', '.join(domains)}. Target: "
        + json.dumps({"aa_model_id": request.model_id, "name": request.model_name, "slug": request.model_slug,
                      "metrics": metrics})
        + '. Return only JSON, with no commentary or Markdown. If no usable evidence exists, return {"claims": []}. '
        'Format example only (not model evidence): {"claims": [{"metric": "max_input_tokens", "value": 123, '
        '"exact_version": "example-model-001", "source_url": "https://example.com/spec", '
        '"excerpt": "example-model-001 input token limit 123"}]}. '
        "Use actual positive integer token limits or documented strings for deployment/residency. "
        "max_input_tokens means the input token limit; max_output_tokens means the output token limit. "
        "context_window means explicitly documented combined input-plus-output capacity; never infer it from an input limit. "
        "Use literal short source excerpts containing the exact model version, metric and value. "
        "Do not substitute related versions or report benchmark scores. Omit unsupported claims. "
        "Python independently checks URLs, excerpts, dates and version matching."
    )


async def fetch_official_page(url, domains, *, transport=None):
    """Resolve only Google's grounding redirect and allowlisted HTTPS docs."""
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, transport=transport) as client:
        for _ in range(3):
            parsed = urlparse(url)
            proxy = parsed.scheme == "https" and parsed.hostname == "vertexaisearch.cloud.google.com" and parsed.path.startswith("/grounding-api-redirect/") and parsed.port in (None, 443) and not parsed.username and not parsed.password
            if not proxy and not official_url(url, domains):
                raise ValueError("Source is outside official-domain allowlist.")
            async with client.stream("GET", url, headers={"Accept": "text/html,text/plain"}) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = str(response.url.join(response.headers.get("Location", "")))
                    continue
                if response.status_code != 200 or proxy:
                    raise ValueError("Official page unavailable or redirect unresolved.")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 1_000_000:
                        raise ValueError("Official page exceeds response-size budget.")
                parser = TextExtractor()
                parser.feed(content.decode("utf-8", errors="replace"))
                text = whitespace(" ".join(parser.parts))
                source_date = None
                if response.headers.get("Last-Modified"):
                    try:
                        source_date = parsedate_to_datetime(response.headers["Last-Modified"]).date().isoformat()
                    except (ValueError, TypeError):
                        pass
                dates = re.findall(r"(?:last updated|updated on)\s*:?\s*(\d{4}-\d{2}-\d{2})", text, re.I)
                if dates:
                    source_date = max(dates)
                return {"url": str(response.url), "text": text, "source_date": source_date}
    raise ValueError("Official source redirect limit exceeded.")


class VertexGroundingBackend:
    is_live = True

    def __init__(self, config: VertexConfig, budget: CallBudget):
        self.config, self.budget = config, budget

    async def search(self, prompt):
        """One generateContent call with Google Search only, no custom functions."""
        from google import genai
        from google.genai import types
        self.budget.reserve(len(prompt))
        options = types.HttpOptions(api_version="v1", timeout=int(self.config.timeout_seconds * 1000),
                                    retry_options=types.HttpRetryOptions(attempts=1))
        # LOW is documented for this exact model. Do not guess other models' settings.
        thinking = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW) if self.config.grounding_model == "gemini-3.5-flash" else None
        generation = types.GenerateContentConfig(max_output_tokens=min(self.config.max_output_tokens, 1024),
            thinking_config=thinking, tools=[types.Tool(google_search=types.GoogleSearch())])
        # JSON + Search support on this Vertex v1 path is not yet verified.
        # Keep grounding enabled rather than silently dropping it for a schema.
        async with genai.Client(vertexai=True, project=self.config.project, location=self.config.location,
                                http_options=options).aio as client:
            response = await asyncio.wait_for(client.models.generate_content(
                model=self.config.grounding_model, contents=prompt,
                config=generation), timeout=self.config.timeout_seconds)
        candidates = response.candidates or []
        metadata = candidates[0].grounding_metadata.model_dump(mode="json", exclude_none=True) if candidates and candidates[0].grounding_metadata else {}
        usage = response.usage_metadata.model_dump(mode="json", exclude_none=True) if response.usage_metadata else {}
        diagnostics = {
            "model_version": getattr(response, "model_version", None),
            "candidates": [{"index": getattr(c, "index", None),
                "finish_reason": getattr(getattr(c, "finish_reason", None), "value", getattr(c, "finish_reason", None)),
                "finish_message": getattr(c, "finish_message", None)} for c in candidates],
            "request": {"model": self.config.grounding_model, "api_version": "v1",
                "max_output_tokens": generation.max_output_tokens,
                "thinking_level": thinking.thinking_level.value if thinking else None,
                "response_mime_type": generation.response_mime_type,
                "response_schema_configured": False, "tools": ["google_search"], "retries": 0},
        }
        return public_diagnostics({"text": response.text or "", "metadata": metadata, "usage": usage,
                                   "diagnostics": diagnostics})


class OfficialSpecService:
    def __init__(self, backend, *, allow_live=False, max_candidates=2, max_grounding_calls=2,
                 max_reported_queries=4, max_source_age_days=180, fetcher=fetch_official_page):
        if not 0 <= max_candidates <= 2 or not 0 <= max_grounding_calls <= 2:
            raise ValueError("Official lookup is limited to two candidates and two grounding calls.")
        self.backend, self.allow_live = backend, allow_live
        self.max_candidates, self.max_calls = max_candidates, max_grounding_calls
        self.max_reported_queries, self.max_source_age_days = max_reported_queries, max_source_age_days
        self.fetcher = fetcher
        self.calls = 0
        self.searched = set()
        self.cache, self.telemetry = {}, []
        self.lock = asyncio.Lock()

    async def lookup(self, request: SpecRequest):
        async with self.lock:
            return await self._lookup(request)

    async def _lookup(self, request: SpecRequest):
        key = (request.snapshot_id, request.model_id, request.metrics)
        if key in self.cache:
            return self.cache[key]
        mode = "live" if getattr(self.backend, "is_live", False) else "offline_fixture"
        result = {"model_id": request.model_id, "snapshot_id": request.snapshot_id,
                  "records": {}, "grounding_metadata": {}, "verification_mode": mode,
                  "diagnostics": {"failure_classifications": [], "metric_failures": {}, "warnings": []}}
        diagnostics = result["diagnostics"]
        metrics = tuple(sorted(set(request.metrics) & SPEC_METRICS))
        def failure(category):
            if category not in diagnostics["failure_classifications"]:
                diagnostics["failure_classifications"].append(category)

        def unknown(reason, category=None):
            if category:
                failure(category)
            diagnostics["primary_failure"] = category or reason
            result["records"] = {m: asdict(SpecEvidence(request.model_id, request.snapshot_id, m, reason=reason, verification_mode=mode)) for m in metrics}
            self.cache[key] = result
            return result
        if not metrics:
            return unknown("no_relevant_requirement")
        if mode == "live" and not self.allow_live:
            return unknown("live_lookup_not_approved")
        domains = OFFICIAL_DOMAINS.get(request.provider.casefold())
        if not domains:
            return unknown("provider_official_domains_unconfigured")
        if self.calls >= self.max_calls or (request.model_id not in self.searched and len(self.searched) >= self.max_candidates):
            return unknown("grounding_budget_exhausted")
        self.calls += 1
        self.searched.add(request.model_id)
        # Reserve before awaiting so concurrent researchers cannot exceed the cap.
        prompt = discovery_prompt(request, domains, metrics)
        started = datetime.now(timezone.utc)
        telemetry = {"model_id": request.model_id, "mode": mode, "status": "unknown"}
        try:
            response = public_diagnostics(await self.backend.search(prompt))
            diagnostics["generation"] = response.get("diagnostics", {})
            diagnostics["visible_text"] = response.get("text", "")
            candidates = diagnostics["generation"].get("candidates", [])
            finish = candidates[0].get("finish_reason") if candidates else None
            if finish is None:
                diagnostics["warnings"].append("finish_reason_unavailable")
            metadata = response.get("metadata", {})
            result["grounding_metadata"] = metadata
            telemetry["usage"] = response.get("usage", {})
            diagnostics["usage"] = telemetry["usage"]
            limit = diagnostics["generation"].get("request", {}).get("max_output_tokens")
            visible = telemetry["usage"].get("candidates_token_count")
            thoughts = telemetry["usage"].get("thoughts_token_count")
            if type(limit) is int and type(visible) is int and type(thoughts) is int and visible + thoughts > limit:
                diagnostics["warnings"].append("reported_output_plus_thoughts_exceeds_configured_max")
            telemetry["reported_search_queries"] = len(metadata.get("web_search_queries", []))
            telemetry["internal_query_cap_enforceable"] = False
            if not metadata.get("grounding_chunks") or not metadata.get("grounding_supports"):
                failure("missing_grounding_citations")
            if finish is not None and finish != "STOP":
                return unknown("incomplete_generation", "incomplete_generation")
            if telemetry["reported_search_queries"] > self.max_reported_queries:
                return unknown("provider_search_query_budget_exceeded")
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.get("text", "").strip())
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return unknown("malformed_json", "malformed_json")
            if not isinstance(parsed, dict) or set(parsed) != {"claims"} or not isinstance(parsed["claims"], list) or len(parsed["claims"]) > 10:
                return unknown("invalid_claim_structure", "unverified_specification")
            claims = parsed["claims"]
            fields = {"metric", "value", "exact_version", "source_url", "excerpt"}
            if any(not isinstance(c, dict) or set(c) != fields
                   or not all(isinstance(c[k], str) for k in fields - {"value"})
                   or type(c["value"]) not in (int, str) for c in claims):
                return unknown("invalid_claim_structure", "unverified_specification")
            if "missing_grounding_citations" in diagnostics["failure_classifications"]:
                return unknown("missing_grounding_citations")
            if not claims:
                return unknown("unverified_specification", "unverified_specification")
            chunks = metadata.get("grounding_chunks", [])
            supports = metadata.get("grounding_supports", [])
            supported = {i for s in supports if s.get("segment", {}).get("text") and s["segment"]["text"] in response.get("text", "") for i in s.get("grounding_chunk_indices", [])}
            if not supported:
                return unknown("missing_grounding_citations", "missing_grounding_citations")
            pages = {}
            for i in sorted(supported)[:3]:
                if not isinstance(i, int) or i < 0 or i >= len(chunks):
                    continue
                uri = chunks[i].get("web", {}).get("uri", "")
                try:
                    pages[i] = await self.fetcher(uri, domains)
                except Exception:
                    failure("official_source_unavailable")
            for metric in metrics:
                accepted = []
                mismatched_version = False
                for claim in claims:
                    if not isinstance(claim, dict) or claim.get("metric") != metric:
                        continue
                    version = claim.get("exact_version", "")
                    excerpt = whitespace(claim.get("excerpt", ""))
                    value = claim.get("value")
                    if normalized(version) != normalized(request.model_slug):
                        mismatched_version = True
                        continue
                    if not 1 <= len(excerpt) <= 700:
                        continue
                    if not re.search(r"(?<![\w.-])" + re.escape(version) + r"(?![\w.-])", excerpt, re.I) or not re.search(LABELS[metric], excerpt, re.I):
                        continue
                    if re.search(r"\b(deprecated|retired|obsolete|superseded)\b", excerpt, re.I):
                        continue
                    if metric in ("context_window", "max_input_tokens", "max_output_tokens"):
                        if type(value) is not int or value <= 0 or not re.search(r"(?<![\d\-\u2212])" + re.escape(str(value)) + r"(?!\d)", excerpt.replace(",", "")):
                            continue
                    elif not isinstance(value, str) or value.casefold() not in excerpt.casefold():
                        continue
                    elif re.search(r"\b(no|not|cannot|unsupported|unavailable|except|excluding)\b|n't", excerpt, re.I):
                        continue
                    for index, page in pages.items():
                        if not official_url(page["url"], domains) or page["url"].split("#")[0] != str(claim.get("source_url", "")).split("#")[0] or excerpt not in whitespace(page["text"]):
                            continue
                        if not any(index in s.get("grounding_chunk_indices", []) and excerpt in s.get("segment", {}).get("text", "") for s in supports):
                            continue
                        try:
                            age = (started.date() - datetime.fromisoformat(page["source_date"]).date()).days
                        except (ValueError, TypeError, KeyError):
                            continue
                        if not 0 <= age <= self.max_source_age_days:
                            continue
                        accepted.append(SpecEvidence(request.model_id, request.snapshot_id, metric, value, version,
                            page["url"], excerpt, source_date=page["source_date"], verification_status="verified",
                            reason="grounded_exact_version_official_excerpt", verification_mode=mode))
                if accepted and len({str(a.value) for a in accepted}) == 1:
                    result["records"][metric] = asdict(accepted[0])
                else:
                    category = ("version_mismatch" if mismatched_version else "official_source_unavailable"
                                if not pages else "unverified_specification")
                    failure(category)
                    diagnostics["metric_failures"][metric] = category
                    result["records"][metric] = asdict(SpecEvidence(request.model_id, request.snapshot_id, metric,
                        reason="conflicting_official_values" if accepted else category, verification_mode=mode))
            telemetry["status"] = "completed"
            self.cache[key] = result
            return result
        except Exception as error:
            telemetry["error"] = safe_error(error)
            return unknown("grounding_or_source_verification_failed", "unverified_specification")
        finally:
            telemetry["elapsed_seconds"] = round((datetime.now(timezone.utc) - started).total_seconds(), 3)
            telemetry["diagnostics"] = deepcopy(diagnostics)
            self.telemetry.append(telemetry)
