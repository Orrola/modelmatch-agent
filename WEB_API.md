# ModelMatch web application and Project 1-compatible chat API

## Reliability metadata

Stage 1 keeps per-model deadlines separate from the complete workflow deadline:
`model_request_timeout` identifies a propagated model-call timeout, while
`workflow_timeout` identifies expiry of the workflow wrapper. Diagnostics preserve the
principal timeout and a metadata-only cause chain; an internal cancellation does not
replace the timeout, and outward cooperative cancellation remains distinct.

Lead parse records may include `output_diagnostics`: response character count, a
Markdown-fence flag, JSON error coordinates, safe schema paths and generation/validation
categories. `length` termination plus invalid output is `incomplete_generation`; syntax
and schema outcomes remain separately visible. Missing finish metadata stays unknown.
These observations never repair, retry or accept an output. Strict SDK parsing and
Lead semantic checks still determine acceptance. No raw response or reasoning text is
included. Lead parse now temporarily uses LOW reasoning on the existing model; its
settings are restored in finally on success, error or cancellation. Dispatch, researchers,
Review and Writer retain their prior settings. Output limits, deadlines and retries are
unchanged. This is local offline validation, not a deployed or live-tested change.

The isolated experiment can be prepared without credentials or model calls:

```sh
.venv/bin/python -m scripts.lead_parse_experiment --manifest .cache/stage2-lead-parse/cases.json
```

Supply a private manifest with four `cases` named `financial`, `coding`,
`customer_support`, and `ecommerce`. Each case needs a `request` using the existing
WebInput fields, `provenance`, and `expected_input_hash` (SHA256 of WebInput.prompt()).
An optional `baseline` must match that hash, model, 2048 output limit and 30-second
timeout. Optional `expectations` provide independent industry/task/constraint/workload
checks. Raw requests and artifacts belong in ignored local storage, not the submission.

The command defaults to preflight. Live execution additionally requires both `--live`
and `--approve-billable`, only after separate authorization. It permits at most four
sequential parse calls, one per case, with no retries, AA, Grounding or full workflow.
The first failed case stops the batch. SDK acceptance, observed eight-field presence,
business validation and extraction correctness are separate results. Missing semantic
expectations require manual review; historical comparisons are not randomized A/B
evidence. Never treat missing usage as zero or a successful parse as a correct recommendation.

Analysis request bodies, endpoints and SSE framing are preserved. `/chat` now restores
the confirmed Project 1 shape. A server-generated `run_id` correlates SSE events and
final analysis results; `/chat` keeps correlation in internal diagnostics and tool identities.
Streaming responses expose `X-ModelMatch-Run-ID`. `/run` forwards that same identity.
Final results include `diagnostics` (stage history, current states, first observed failure),
`classification`, and `writer_error` when applicable. The first observed failure may have
been recovered by an authorized follow-up; inspect the final states and workflow status too.

`completed` means generation returned, `accepted` means the controller's checks passed.
These precise values live in diagnostic states and the additive SSE `phase_status`.
Legacy SSE `status` keeps its existing vocabulary: accepted maps to completed,
generation completion stays running until acceptance, fallback maps to failed, and
not_reached maps to skipped. New clients use phase_status for the finer distinction.
`failed`, `cancelled`, `not_reached`, intentional `skipped`, and Writer `fallback` remain
distinct. Review acceptance alone does not approve the subsequent Decision evidence gate.
Writer fallback preserves deterministic scores but is not successful Writer generation.
Stable Writer error categories include `provider_error`, `timeout`, `schema_validation_error`,
`evidence_validation_error` and `budget_exceeded`; unknown errors remain `execution_error`.

Structured application logs contain metadata only, not request text, model output or hidden
reasoning. Call records distinguish adapter invocation and available provider response metadata
from controller acceptance. Missing finish reasons/model versions remain null. LiteLLM's raw
non-streaming response metadata is observed before the installed adapter discards it; SDK
upgrades require the adapter regression test. Numeric reasoning-token usage may be retained
when supplied, never reasoning text. `model_requests` remains a reservation count, not a
guaranteed count of provider-processed or billable calls. Existing opt-in CLI response capture
is separate from normal production logging.

Classification policy `modelmatch-task-classification-v1` resolves only the overlap between
`reasoning_analysis`, `specialized_domain`, and `mixed_or_unknown`: explicit cross-domain
scope/multiple recognized domains wins; one recognized domain selects specialized work;
domain-independent analytical work selects reasoning; otherwise the conservative mixed/unknown
default applies. The recognized vocabulary covers finance, legal, healthcare, engineering,
economics and strategy/operations; it is not an exhaustive semantic classifier. Other proposed
primary task types are retained. Results record the proposal, resolution and rule. This policy
does not establish benchmark relevance, change the weight table, or override user alpha.
The same prepared evidence and weights still use the unchanged deterministic Decision engine.

Uvicorn access logs strip query strings, including compatibility `/run` inputs. Cloud Run's
own request-log handling remains a platform concern: prefer POST for sensitive requirements
and review platform log access/retention separately. Do not assume application redaction
removes query strings from upstream infrastructure logs.

Start the real local application from the project directory:

```sh
MODELMATCH_OFFLINE=0 GOOGLE_CLOUD_PROJECT=ieor4570-yg3133 GOOGLE_CLOUD_LOCATION=global .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://127.0.0.1:8000/modelmatch`, enter a task, and click **Run analysis**. Live Mode is the default when `MODELMATCH_OFFLINE` is unset or `0`; the explicit `0` above also overrides an old testing setting. Existing local `.env` supplies AA_API_KEY and configured Gemini model IDs. Vertex uses the existing ADC identity, not a new Gemini API key. Credentials remain server-side. If ADC or API access is unavailable, the analysis reports failure rather than switching to fictional models.

Starting the server, opening the page, and health/config checks do not generate model requests or fetch AA data. Clicking Run analysis is the explicit action that submits `approve_live: true` in Live Mode. The analyze API still rejects direct live requests without that flag. The separate `/chat` adapter uses the server-side evaluation gate described below. The approved Lead → parallel A/B/C → same Lead Review → Decision → Writer workflow then streams its actual result to the three views. Alpha adjustments use the deterministic recalculation endpoint and do not run Gemini again.

Both `/` and `/modelmatch` serve ModelMatch AI. `GET /run?mode=modelmatch&question=...` remains a compatibility SSE adapter over the same service, including the previous start/run_id and done/markdown/result fields; omitting mode now also selects ModelMatch. Explicit GET research starts live work just as an explicit POST does. The old Wikipedia mode and context-dump/browser-panel routes are removed. Grounding remains disabled in this web flow; missing official specifications and unknown hard constraints retain their existing evidence/eligibility behavior.

## Explicit offline testing only

Synthetic execution requires deliberately setting `MODELMATCH_OFFLINE=1`. It is never a fallback for failed authentication, model requests, or AA access. Test output is clearly labeled synthetic and is not live provider acceptance. Do not use the following test-mode commands for normal application use.

Run regression and HTTP checks without provider calls:

```sh
.venv/bin/python -m unittest discover -s tests -q
MODELMATCH_OFFLINE=1 .venv/bin/python -m scripts.web_smoke
```

The HTTP smoke script starts a temporary single-worker server and checks loopback HTTP, assets, SSE, Project 1-compatible `/chat`, and deterministic weight changes. It does not call Gemini or AA. The test suite uses scripted SDK models and mocked HTTP transports.

Provider calls may incur charges only after a live analysis is initiated. No live end-to-end acceptance or deployment is implied by the offline wiring tests.

## Endpoints

- `GET /modelmatch`: dedicated UI, with local JS/CSS and no CDN runtime dependency.
- `GET /healthz`: local process health only; does not verify credentials or providers.
- `GET /api/modelmatch/config`: execution mode, confirmed chat-shape status, evidence retention, and disabled Grounding state.
- `POST /api/modelmatch/analyze`: JSON requirements, SSE response. Requests never use GET query parameters for requirement text.
- `POST /api/modelmatch/recalculate`: original analysis ID and nullable `user_alpha`; `null` restores the existing task policy. No research or Writer calls occur.
- `POST /chat`: Project 1-compatible, bounded conversation adapter, described below.

Analysis request example:

```json
{
  "question": "Analyze financial documents for a finance team.",
  "monthly_budget": 100,
  "monthly_requests": 1000,
  "avg_input_tokens": 2000,
  "avg_output_tokens": 500,
  "ttft": 2,
  "output_speed": 50,
  "context_window": 100000,
  "hard_constraints": ["context_window"],
  "user_alpha": null,
  "approve_live": true
}
```

All numeric fields are optional JSON numbers, finite and nonnegative (context must be positive). Alpha is in [0,1]. Omit unspecified fields; missing values never become zero. A hard flag requires its target. Structured inputs take precedence over parsed text for the same metric and are retained as explicit user quotes. Other requirements remain the Lead's grounded interpretation. The same Lead still classifies the task and reviews evidence. Monthly cost requires the existing three workload inputs; missing essential information returns clarification rather than guessing. The UI appends a clarification answer to the original task and starts a fresh analysis only when Continue with clarification is clicked.

SSE frames use `data: <JSON>`, blank-line separators, and comment heartbeats. Types are `start`, existing `activity`/`context`, `stage`, `interpretation`, `tool_trace`, terminal `done`, or terminal `error`. `done` contains `analysis_id` (nullable if the stored result exceeds the memory envelope) and the existing workflow `result` augmented with `plan`, `execution_mode`, `integration_usage`, and `tool_calls`. A workflow error can be represented by `done.result.status=error`; receiving `done` alone never proves success. Client disconnect cancels the worker task; ambiguous remote cancellation cannot guarantee a provider request already sent is unbilled. There is no reconnect/replay of a disconnected SSE run.

Each tool trace contains actual model call ID, attributed agent and independent context ID, tool name, parameters, result, status, start/end epoch timestamps, and elapsed seconds. Nested researcher tools remain separate from Lead agent-tools. Proposed calls are not counted as executed. Incomplete hooks become `not_executed` or `interrupted`. Long arguments/results are explicitly marked as truncated; they are previews, not a lossless audit archive. Traces do not expose hidden reasoning. Context events signal updates; this UI does not expose the full system prompts/context-panel transcript.

Recalculation request:

```json
{"analysis_id": "opaque-id-from-done", "user_alpha": 0.7}
```

It returns the original analysis ID, the existing engine's decision, `research_rerun: false`, `writer_alpha`, and `writer_explanation_stale`. The original result and Writer report are retained unchanged. Only the selected ranking changes. Candidate status groups, evidence, operational penalties, alpha policy and sensitivity use the existing engine, not frontend arithmetic. `null` resets to the task default rather than a hardcoded 0.60. An expired/evicted/missing ID returns 404; an analysis without decision evidence returns 409.

## Deterministic recommendation selection

Successful Decision results include additive `selection`, `selector`, `writer_status`,
`report_basis`, and `report_fallback` fields. Original `decision`, complete raw rankings,
evidence and scores are preserved. `selection` contains `selection_id`, snapshot fingerprint,
mapping/policy versions, coverage counts, recommendation slots and separate unscored
Potential Alternatives. Slot order is `best_overall`, `lower_cost_alternative`,
`different_family`: zero to three slots may be selected. Role order is not Raw Ranking
order. Missing slots carry reasons. Family grouping is curated AA-label evidence, not
verified underlying model equivalence; new snapshots do not inherit older audited groups.

`selector.status` is `available`, `limited_metadata`, or `unavailable`. Unmapped families
remain unknown. Metadata/coverage/Selector errors preserve Decision and return a sanitized
category and phase under `selector.error`. Selector is local deterministic processing,
not an Agent stage or additional provider call. If unavailable, `selection=null`, Writer
is `skipped`, and the report is explicitly a deterministic fallback. Real Writer rejection
remains `writer_status=fallback`, `writer_fallback=true`; neither is accepted generation.
A valid zero-slot selection allows strict Writer validation of empty candidate/evidence
lists with nonempty next steps, without supporting numeric recommendations.

Writer inputs, acceptance checks and rendering use the same canonical selection.
Candidate IDs/order must match exactly and every observed evidence ID for those candidates
is required. Potential Alternatives are excluded from Writer candidates and keep `S=null`.

Recalculation returns existing fields plus updated `selection`/`selector`,
`writer_selection_id`, and `writer_narrative_available` (an accepted original Writer output
exists). Decision and Selector reuse privately frozen prepared evidence, exact snapshot
pages, identity sidecar, family mapping and version identities. There is no AA/Gemini call
or current mapping reload. `writer_explanation_stale` is true if alpha or selection identity
changes, or selection is unavailable; a weight-source change can change identity too.
Original analysis/narrative remains immutable. Missing or incompatible context reports
Selector-unavailable while preserving recalculated raw Decision. Existing retention/size
limits and single-worker in-memory state still apply; instances do not share sessions.

SSE `done.result` and compatibility `GET /run` retain the additive selection fields and
full stage/trace envelopes. `/chat` renders the canonical recommendation in `response`
and projects actual tool calls; it does not expose internal `result` or diagnostic state.

## Project 1-compatible `/chat` contract

The instructor confirmed the Project 1 response shape and agent attribution for nested
sub-agent tool calls. This confirms this interface requirement, not every Project 2 rubric item.
This endpoint is not an OpenAI Chat Completions implementation.

Request (only these fields are accepted):

```json
{"message": "Analyze financial documents for a finance team.", "session_id": null}
```

`message` is a nonblank string of 1–6,000 characters. `session_id` is optional/null for a
new conversation; reuse the returned opaque ID for subsequent turns. Credential-like
messages are rejected without echoing their contents. Do not send `approve_live`,
`analysis_id`, or structured analysis fields to this endpoint.

Successful turns return exactly these top-level fields:

```json
{"response": "Answer or clarification text", "session_id": "opaque-chat-id", "tool_calls": []}
```

`response` is the canonical report, clarification, saved-evidence answer, or a clearly
labeled safe failure/fallback. A rejected Writer remains a failure; the adapter never
labels its fallback as accepted generation. There is no `reply`, `result`, `contract`,
`analysis_id`, or diagnostic envelope in this response. The UI continues using analyze/SSE.
`GET /api/modelmatch/config` reports `chat_contract: project1-chat-v1` and
`contract_verified: true` for this confirmed shape only.

`tool_calls` contains this turn's actual Lead and nested Researcher calls with `agent`,
`call_id`, `context_id`, `tool`, projected `arguments`/`result`, status and execution timing.
Unexecuted proposals are excluded. The whitelist omits free-form task text, rationales,
prompts, hidden reasoning, credentials and raw provider bodies. Large collections are
explicitly bounded; these records are privacy-preserving previews, not complete archives.
Evidence-only replies and deterministic weight adjustments return no fabricated tools.

### Conversation state and task scope

Chat sessions are separate from analysis evidence sessions. Defaults: 30-minute inactivity
TTL, at most 100 conversations per instance, last 10 visible messages, one active request
per session. Message excerpts are bounded; confirmed current-task user requirements and
validated plan values remain separate from the truncated history. The effective task is
capped at 6,000 characters; overflow is rejected, never silently discarded.

Clarification replies continue the pending task. Amendments retain unchanged confirmed
requirements; changed targets must be anchored in the latest user message or clarification
is requested before research. Assistant messages are background only, never user constraints.
An explicit new task or complete fresh declaration starts a new task scope without prior
constraints. Ambiguous changes of domain/purpose ask whether to start an independent task.
The same visible conversation survives; old-task text is excluded from the new parse context.
Scope routing is intentionally conservative, not an unrestricted natural-language intent model.

Questions about saved recommendations/scores/evidence use the frozen analysis, not a fresh
Gemini or AA request. Unsupported official specifications remain unknown. `Set alpha to 0.70`
uses the existing deterministic Decision/Selector on frozen evidence; the original Writer
narrative is marked stale and the adjusted report is explicitly deterministic. Other task
changes may start a new bounded workflow. Expired/evicted evidence is reported unavailable;
it is never silently refreshed. No closed workflow is resumed: each new analysis retains
the same Lead within that run and fresh independent A/B/C contexts.

Unknown chat IDs return 404; recently expired IDs return 410 while bounded expiry markers
remain retained, then 404. Busy-session turns return 409, capacity/configuration failures
503, disabled evaluation 403, exhausted research allowance 429, oversized task context 413,
and malformed requests 422. Non-2xx errors use safe FastAPI-style `detail`, not a fake answer.
Accepted turns with workflow/provider failures keep the three-field response and any actual
partial tool calls. Cancellation releases locks/capacity and does not refund consumed allowance.

### Server-side evaluation access

The grader does not need an undocumented approval field. An operator must explicitly set:

```text
MODELMATCH_CHAT_EVALUATION_ENABLED=1
MODELMATCH_CHAT_EVALUATION_MAX_RUNS=3
```

The default is disabled. The default research allowance is three workflow starts per
process, shared across all sessions; valid configured limits are 1–100. Invalid values
fail closed. Creating a session, toggling the evaluation flag, or a failed/cancelled run
does not refill the counter. Each admitted workflow, including a model-based clarification,
consumes one start before execution; existing 24-generation, timeout, zero-retry and
concurrency limits remain in force. Read-only saved-evidence turns do not spend research
allowance and may continue after it is exhausted; disabling evaluation blocks all chat turns.
No request body can enable evaluation or override its allowance.

These are per-process limits, not authentication, durable quotas or a global/dollar spending
cap. Restart/new instances reset counters and lose sessions; IDs can fail on another worker.
Configure evaluator access and instance policy separately before deployment. This change
provisions no storage, IAM, secrets, quotas or public access. `/api/modelmatch/analyze`
retains its existing `approve_live` requirement; `/run` and SSE/recalculate contracts are unchanged.

## Execution and Cloud Run preparation

Production startup:

```sh
.venv/bin/uvicorn app:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1 --timeout-keep-alive 5
```

`python app.py` also honors `PORT` and binds 0.0.0.0. The Dockerfile uses the existing lockfile; building requires dependency/image downloads and has not been performed as part of offline verification. ADC must come from the runtime service account, never a key bundled into the image. `.dockerignore` and `.gcloudignore` exclude local secrets, caches, development docs and tests. Docker COPY lists the runtime source explicitly; no runtime or test dependency on `docs/` exists. Bundled `examples/offline-aa.json` is synthetic and used only when offline mode is explicitly selected.

Each analysis, including compatibility `/run`, uses the same service limits: 24 model generations, 30-second provider requests, 180-second workflow research, 190-second outer timeout, six researcher runs and one follow-up round. There are no configured provider retries. Two concurrent analyses and six starts/minute per process are allowed. POST input bodies are capped at 16000 bytes, question length at 6000 characters, and SSE queues at 512 events. Event overflow stops research. Health checks and deterministic recalculation do not consume provider quota.

Evidence sessions are **ephemeral, single-process memory**, retained for at most 30 minutes, eight sessions, and approximately 64 MiB of serialized saved content (not a guarantee on Python heap size). Results over 32 MiB are not retained for recalculation. Eviction/restart invalidates analysis IDs; IDs are unguessable bearer capabilities and should not be shared. Rate/concurrency limits are process-local. AA cache in `/tmp/modelmatch-aa` is an optimization; an empty cache can fetch the live API with AA_API_KEY. No session correctness relies on disk persistence.

Before Cloud Run production deployment: add authentication/access control, tenant-scoped shared evidence storage with TTL and encryption, distributed request budgets/rate limits, and authenticated trace access. Multiple instances/workers are unsupported for reliable recalculation until shared storage is added. Validate the container, set an HTTP timeout exceeding the bounded workflow, review concurrency, verify the runtime service account/Vertex permissions and AA secret injection, and verify the course contract. Do not expose this unauthenticated research endpoint publicly as-is. No IAM/API changes, billable tests, or deployment are automatic.

### Runtime identity, origin and evaluator setup

Install the locked dependencies with `uv sync --locked` for local use; the container
uses `uv sync --locked --no-dev`. Keep `MODELMATCH_OFFLINE=0` in production.
Supply `GOOGLE_CLOUD_PROJECT=ieor4570-yg3133` and the configured Vertex location
explicitly rather than relying on a local gcloud installation. Preserve the configured
Gemini model IDs. Startup, `/healthz`, static assets and `/api/modelmatch/config`
do not initiate Gemini or AA analysis requests.

Cloud Run ADC comes from its attached runtime service account, not a developer's local
ADC file. Inject `AA_API_KEY` server-side through Secret Manager or secure runtime
configuration; never bundle `.env`, downloaded service-account keys or credentials.
Manually verify least-privilege Vertex prediction access (typically
`roles/aiplatform.user`, including `aiplatform.endpoints.predict`) and, when using
Secret Manager, `roles/secretmanager.secretAccessor` on the individual AA secret.
Verify `serviceusage.services.use` where required. Check Vertex AI, Cloud Run,
Artifact Registry and any used Secret Manager/Cloud Build APIs for the existing
deployment path. These are prerequisites to verify, not permissions or services
configured by the application.

For the current TLS-ingress service, the exact external origin is:

```text
MODELMATCH_PUBLIC_ORIGIN=https://modelmatch-agent-git-978311583991.europe-west1.run.app
```

Protected POST requests require matching Host and matching Origin when supplied.
Client-supplied forwarded headers do not expand this allowlist. Leave the setting
empty for local same-origin development; do not use wildcard CORS or
`FORWARDED_ALLOW_IPS=*` to bypass an origin error. Origin checking is not authentication.

For evaluator `/chat` access, explicitly configure the server-side evaluation flag and
bounded allowance documented above; the grader sends only `message` and optional
`session_id`. The allowance applies to `/chat`, not all other paid entry points.
Protect analysis, `/run`, recalculation and traces through an appropriate access-control
strategy as well. Keep one worker and accept ephemeral sessions for a limited
single-instance evaluation; scaling requires shared session state and distributed
budgets. Instance restarts reset local counters, so they are not a global spending cap.
Choose and verify platform timeout, concurrency and evaluator access separately;
no configuration change is implied by these instructions.

For provider-free container checks, start the image without credentials and request only
`/healthz`, `/api/modelmatch/config` and `/modelmatch`. Verify non-default `PORT`, static
assets, non-root execution and excluded artifacts. A healthy process does not establish
successful live research. Avoid sensitive input in `/run` query strings; platform access
logs may retain URLs even when application diagnostics omit request bodies.


## Recommendation presentation metadata

An additive `model_identity` projection accompanies successful Selector results and
recalculation responses. It copies the validated, frozen sidecar binding and exact model
identities, creator fields, reviewed configuration labels and family statuses. Its `families`
map contains existing curated family labels and explicit `model_ids` in exact-ID order.
This is a read-only presentation projection, not a new family grouping or selection policy.
The projection does not contain snapshot pages, credentials, prompts or benchmark scores.
It is excluded from canonical selection hashing and Writer input; numeric evidence stays
in the original Decision. Selector failure returns `model_identity: null`.

The UI checks snapshot, retrieval, data-mode and mapping compatibility before using these
identities. Missing/incompatible metadata stays unknown. Family expansion reads explicit
server membership; JavaScript does not normalize names or infer grouping. Potential
Alternatives render the existing U-only/G-only and eligibility buckets, initially two per
bucket with expansion only to returned entries. Backend omissions remain disclosed; there
is no hidden re-fetch. Current and original Raw Rankings keep server ordering and scores.
`GET /recommendation-views.js` serves the local presentation component; existing application
endpoints and SSE framing are unchanged. The confirmed `/chat` shape is documented above; other course deliverables still require verification.
