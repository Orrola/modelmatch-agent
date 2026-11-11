# ModelMatch AI

An evidence-grounded LLM selection workspace for product managers, engineers, and technical decision-makers. Describe a task, compare models against the available Artificial Analysis (AA) evidence, and inspect the tradeoffs behind a conditional shortlist.

The web application has Overview, Comparison, Evidence, and model-detail views. Live Mode uses Vertex AI with Application Default Credentials (ADC). Synthetic data is available only for explicitly selected offline tests; provider failures never switch to fictional models.

## Quick start

Requirements: Python 3.10+, [uv](https://docs.astral.sh/uv/), an existing Google Cloud project with appropriate Vertex access, ADC, and an AA API key. Installation downloads dependencies; running the offline tests does not require provider credentials.

```sh
uv sync --locked
```

Copy `.env.example` to `.env` only if a local `.env` does not already exist. Set `AA_API_KEY` and the existing project/location as needed. Never commit credentials. ADC can be configured with `gcloud auth application-default login`; no separate Gemini API key is required when Vertex ADC works. This application does not create projects, enable cloud services, or change IAM.

Start the real local web application:

```sh
MODELMATCH_OFFLINE=0 .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Open **http://127.0.0.1:8000/** or **http://127.0.0.1:8000/modelmatch**. Enter a task and click **Run analysis** to initiate live requests. Startup, page loading, and health/config checks do not call Gemini or AA. The configured defaults are `gemini-3.5-flash` for Lead/Writer and `gemini-3.5-flash-lite` for researchers, with `global` as the location fallback. Credentials and actual model access are checked by the provider when a request is made, not by the health endpoint.

Example task: `Analyze financial documents for a finance team.` Optional form fields support monthly budget, workload, mean TTFT, mean output speed, and combined context. Blank fields remain unspecified. Monthly cost needs request volume and both average input/output token counts, plus both token prices. Unsupported official specifications stay unknown. Hard requirements are evaluated separately from soft preferences.

## Architecture

```text
User requirements
  -> Lead parses requirements and classifies the task
  -> parallel Researcher A / B / C, each with a fresh Runner.run context
  -> the same Lead reviews evidence and may request one targeted follow-up round
  -> deterministic Decision Tool
  -> Writer selects evidence-grounded report content
  -> SSE results, model comparison, and inspectable evidence
```

The OpenAI Agents SDK Agent-as-a-Tool pattern is retained: Lead tools launch independent researcher runs. SDK hooks record attributed tool calls and execution intervals. Python owns workflow stages, stage-specific schemas and tool visibility. Parsing/reviewing stages cannot invoke researcher tools. The original instructor starter supplied useful orchestration conventions; its Wikipedia product, data access, prompts, browser assets and unauthenticated context-dump endpoints have been removed.

- **A — General Intelligence:** retrieves original numeric General Intelligence G and retains missing records separately.
- **B — Use-case Fit:** selects a relevant AA Capability Index U with strong/partial/none relevance and an explanation. Supported domains are finance, strategy/operations, legal, healthcare, engineering, and economics. Unsupported tasks never receive an invented U.
- **C — Operational Fit:** inspects pricing, workload-based cost, performance_v3 means and supplied constraints. Context/deployment/residency remain unknown without verified official evidence.
- **Lead Evidence Review:** checks missing data, IDs, versions, relevance and constraints; bounded follow-up does not invent values absent from a fixed snapshot.
- **Decision:** joins evidence by exact AA model ID, preserving snapshot and evidence provenance.
- **Writer:** cannot change canonical ranked model IDs or evidence IDs. The deterministic renderer owns numbers and ordering.

## Decision policy

```text
S = alpha * G + (1 - alpha) * U + O
```

G and U are original AA index points. They are not accuracy percentages. S is a custom product decision score, not an official AA benchmark. Task defaults are provisional policy rather than empirically validated optimal weights:

| Task type | General weight alpha |
|---|---:|
| general_assistant | 0.70 |
| tool_agent | 0.50 |
| reasoning_analysis | 0.50 |
| coding_assistant | 0.40 |
| specialized_domain | 0.30 |
| mixed_or_unknown | 0.60 |

Modes are `task_default`, `user_override`, and `fallback_default`. The user override takes precedence. The slider recalculates with the same evidence, without fetching data or calling Gemini. Reset passes `null` to restore the task default. The original Writer report remains unchanged and is marked stale when it corresponds to different weights. Sensitivity results include alpha=0.50, 0.60, 0.70, and the selected value.

Operational adjustments are deterministic, capped linear penalties, with -15 <= O <= 0:

```text
cost_penalty = -8 * min(1, max(0, (estimated_cost - budget) / budget))
ttft_penalty = -5 * min(1, max(0, (mean_ttft - target) / target))
speed_penalty = -2 * min(1, max(0, (target - mean_speed) / target))
```

These apply only when the corresponding soft target and compatible evidence exist. For a zero upper target, zero actual passes and any positive actual receives the capped deduction; a zero speed minimum passes available nonnegative measurements. Missing evidence is not zero or an automatic zero penalty. Hard constraints are enforced separately: known violations are ineligible; unresolved hard requirements are unverified. Performance comparisons exclusively use performance_v3 **mean** statistics, never legacy medians or P95 claims.

Fully evaluable, provisional, unverified, and ineligible candidates remain separate. A needs valid G; B needs only the selected U and documented relevance; C needs operational evidence sufficient for supplied requirements. There is no all-six-index intersection pool. Counts before shortlist limits are returned. `shortlist_size=6` in the web flow is per category, not a six-model AA snapshot restriction. Prompts use bounded evidence previews rather than the complete raw catalog.

## Data and official specifications

The async AA Free client handles pagination, timeouts, bounded rate-limit retries and caching. Real snapshots retain source URL, retrieval time, original IDs and index versions. The cache is an optimization, not required persistent storage; valid live cache entries can be reused without pretending they are freshly retrieved. API errors never silently use test fixtures. Historical coding/agentic fields and unavailable Capability Indices are not synthesized.

Official-specification infrastructure is retained in `tools/official_specs.py`. It uses a separate Search-only Vertex request and conservative checks of official domains, exact versions, literal excerpts, dates and citations. Its grounding diagnostics retain stopping information and usage where available. Search-generated claims are not verified facts. **Grounding is disabled in the normal web flow.** Previous live discovery returned insufficient citation metadata; official context/input/output/deployment values remain unknown unless independently accepted by the existing verifier. No candidate-model benchmarking is performed.

Data attribution and methodology: [Artificial Analysis](https://artificialanalysis.ai/), [API documentation](https://artificialanalysis.ai/data-api/docs), [Capability Index methodology](https://artificialanalysis.ai/methodology/capability-indices). Verify data redistribution rights before publishing snapshots. Local API payloads and audit artifacts are not included in this repository.

## API and traces

Full English request/response descriptions are in [WEB_API.md](WEB_API.md).

| Endpoint | Purpose |
|---|---|
| `GET /`, `GET /modelmatch` | ModelMatch web application |
| `GET /healthz` | Process health; no provider calls |
| `GET /api/modelmatch/config` | Execution mode and capability flags |
| `POST /api/modelmatch/analyze` | Validated requirements and SSE research |
| `POST /api/modelmatch/recalculate` | Reuse original evidence at a new alpha |
| `POST /chat` | Clearly provisional chat adapter with attributed nested traces |
| `GET /run?mode=modelmatch&question=...` | ModelMatch compatibility SSE, including `done.markdown` and `done.result` |

The compatibility `/run` defaults to ModelMatch, uses the same service/limits, and starts research only when explicitly requested. Wikipedia mode is no longer supported. The primary UI uses POST analyze. Existing ModelMatch GET start/run_id and done/markdown/result fields are retained. Old `/context` and `/context-panel.js` routes are removed; the new UI already exposes bounded technical traces without publishing full agent contexts or prompts.

SSE includes start, activity/context notifications, stage, interpretation, tool_trace, done/error, and heartbeat comments. Receiving HTTP 200 or a `done` event is not proof of successful research: inspect the result status, evidence, and Writer flag. Tool traces retain call IDs, agent/context attribution, parameters, results, statuses and timings; explicitly truncated previews are not lossless audit archives. Client disconnect cancels the worker; an already-issued provider request may still incur usage.

## Known limitations and live validation status

**A live Writer failure has been reported and remains unresolved.** This cleanup neither reproduces it with paid calls nor silently fixes/bypasses it. A rejected/unavailable Writer produces `writer_rejected` and `writer_fallback=true`; the frontend identifies the deterministic fallback. That fallback does not count as successful live Writer verification, even if its numeric report is safely rendered from canonical evidence. Do not label HTTP success or fallback output as complete live success. Older bounded pipeline success is not proof that the reported failure is resolved.

Other limitations: official Grounding citation reliability, exact-version verification gaps, task classification ambiguity, and single-process session state. The current `/chat` is **not yet verified against authoritative course instructions**. A local previous Project 1 implementation uses `message/session_id` and `response/session_id/tool_calls`; the current adapter uses a different documented provisional envelope. See [SUBMISSION.md](SUBMISSION.md) for missing deliverables and verification boundaries.

## Offline verification

```sh
uv lock --check --offline
uv sync --locked --offline
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m scripts.submission_audit
MODELMATCH_OFFLINE=1 .venv/bin/python -m scripts.web_smoke
```

The offline uv commands require an already populated dependency cache. On a fresh machine, use `uv sync --locked` first. Synthetic fixtures are explicitly labeled and never represent real evaluations. Unit tests mock provider calls. `web_smoke` starts a temporary loopback HTTP server in explicit synthetic mode and tests assets, SSE, clarification, traces and weight changes. It is a test, not the normal application startup command or live acceptance.

Optional browser review: `MODELMATCH_OFFLINE=1 .venv/bin/python -m scripts.ui_smoke` requires local Chrome and the installed `websockets` library. It uses an isolated temporary profile. JavaScriptCore tests run when that interpreter is available and otherwise report a skip. No browser test installs software or calls a paid model automatically.

## Repository map

```text
app.py                       FastAPI entry point, root page, compatibility SSE
modelmatch_web.py            HTTP contracts, web hooks, bounded evidence sessions
modelmatch_agents.py         Lead, researcher tools, Writer definitions
modelmatch_schemas.py        Stage outputs, contexts, execution limits
orchestration.py             Parallel runs, same-Lead review, Decision/Writer validation
context_panel.py             Reusable SDK context recording and hooks; no HTTP routes
vertex_runtime.py            ADC configuration, request budgets, sanitized diagnostics
recommendation.py            Writer validation and deterministic report rendering
tools/                      AA access, evidence preparation, decision, official specs
static/                     English HTML/CSS/JS application
tests/                      Offline regression and sanitized/synthetic fixtures
examples/                   Explicit synthetic demonstration data
offline_model.py             Explicit test-mode scripted SDK model
scripts/                    Audits and opt-in operational verification
Dockerfile                  Container startup for a subsequent deployment
WEB_API.md / SUBMISSION.md    Public contracts, limitations and submission checklist
```

## Deployment preparation

No deployment is performed by startup, tests, or cleanup. The container uses Python 3.13, the lockfile, a non-root runtime user and one worker:

See [deployment readiness and operating limits](DEPLOYMENT.md) before exposing the service. Container build/runtime and cloud permissions require separate verification; the local machine used for readiness checks has no Docker executable.

```sh
docker build -t modelmatch-ai .
docker run --rm -p 8080:8080 --env-file .env modelmatch-ai
```

Supply ADC through the runtime identity or an explicit development credential mount; the commands do not bundle local ADC into the image. On Cloud Run use a properly authorized service account and server-side AA secret injection. Never commit or upload `.env`, caches, internal `docs/`, browser artifacts, private keys or service-account JSON. The deployment ignore files limit uploaded/build source files. Preserve local development material outside the submission set.

Startup binds `0.0.0.0:$PORT` (`PORT=8080` in the container); `python app.py` defaults to port 8000. `/healthz` does not attest to provider readiness. The web workflow retains 24 shared model requests, 2048 configured output tokens per request, 30-second provider timeout, 180-second workflow and 190-second outer timeout, at most six researcher runs and one follow-up round. No model retries or full-run retries are automatic. AA retains its separate bounded pagination/retry policy. Usage does not establish an exact dollar cost or total thinking-token ceiling.

The MVP allows two concurrent analyses and six starts/minute per process. Evidence sessions are ephemeral: 30-minute TTL, eight sessions, approximately 64 MiB serialized storage, with a 32 MiB single-entry cutoff. Missing/expired sessions return explicit errors. These limits are not distributed and are not a precise Python heap bound. Multiple instances/workers need shared, tenant-scoped evidence storage for reliable recalculation. Public deployment also needs authentication, trace access controls, distributed budgets, container validation, and runtime permissions/timeouts. GitHub source readiness, deployment readiness and complete live validation are separate milestones.
