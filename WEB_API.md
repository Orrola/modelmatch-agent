# ModelMatch web application and provisional API

Start the real local application from the project directory:

```sh
MODELMATCH_OFFLINE=0 GOOGLE_CLOUD_PROJECT=ieor4570-yg3133 GOOGLE_CLOUD_LOCATION=global .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://127.0.0.1:8000/modelmatch`, enter a task, and click **Run analysis**. Live Mode is the default when `MODELMATCH_OFFLINE` is unset or `0`; the explicit `0` above also overrides an old testing setting. Existing local `.env` supplies AA_API_KEY and configured Gemini model IDs. Vertex uses the existing ADC identity, not a new Gemini API key. Credentials remain server-side. If ADC or API access is unavailable, the analysis reports failure rather than switching to fictional models.

Starting the server, opening the page, and health/config checks do not generate model requests or fetch AA data. Clicking Run analysis is the explicit action that submits `approve_live: true` in Live Mode. The existing API still rejects direct live requests without that flag. The approved Lead → parallel A/B/C → same Lead Review → Decision → Writer workflow then streams its actual result to the three views. Alpha adjustments use the deterministic recalculation endpoint and do not run Gemini again.

Both `/` and `/modelmatch` serve ModelMatch AI. `GET /run?mode=modelmatch&question=...` remains a compatibility SSE adapter over the same service, including the previous start/run_id and done/markdown/result fields; omitting mode now also selects ModelMatch. Explicit GET research starts live work just as an explicit POST does. The old Wikipedia mode and context-dump/browser-panel routes are removed. Grounding remains disabled in this web flow; missing official specifications and unknown hard constraints retain their existing evidence/eligibility behavior.

## Explicit offline testing only

Synthetic execution requires deliberately setting `MODELMATCH_OFFLINE=1`. It is never a fallback for failed authentication, model requests, or AA access. Test output is clearly labeled synthetic and is not live provider acceptance. Do not use the following test-mode commands for normal application use.

Run regression and HTTP checks without provider calls:

```sh
.venv/bin/python -m unittest discover -s tests -q
MODELMATCH_OFFLINE=1 .venv/bin/python -m scripts.web_smoke
```

The HTTP smoke script starts a temporary single-worker server and checks loopback HTTP, assets, SSE, provisional `/chat`, and deterministic weight changes. It does not call Gemini or AA. The test suite uses scripted SDK models and mocked HTTP transports.

Provider calls may incur charges only after a live analysis is initiated. No live end-to-end acceptance or deployment is implied by the offline wiring tests.

## Endpoints

- `GET /modelmatch`: dedicated UI, with local JS/CSS and no CDN runtime dependency.
- `GET /healthz`: local process health only; does not verify credentials or providers.
- `GET /api/modelmatch/config`: execution mode, provisional contract status, evidence retention, and disabled Grounding state.
- `POST /api/modelmatch/analyze`: JSON requirements, SSE response. Requests never use GET query parameters for requirement text.
- `POST /api/modelmatch/recalculate`: original analysis ID and nullable `user_alpha`; `null` restores the existing task policy. No research or Writer calls occur.
- `POST /chat`: **provisional adapter**, described below.

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

## Provisional `/chat` contract

No authoritative Project 2 `/chat` contract was found. Cleanup identified a local previous Project 1 implementation with request fields `message/session_id` and response fields `response/session_id/tool_calls`; this is an observed prior implementation, not an official assignment specification. The current adapter differs and compatibility with the grader is **pending**, not claimed. Cleanup preserves this existing contract rather than silently changing it. This endpoint is not an OpenAI Chat Completions implementation.

Request: the same optional analysis fields, with required `message` replacing `question`. Send the full task plus any clarification; there is no automatic conversation memory. Example:

```json
{"message": "Analyze financial documents for a finance team.", "approve_live": true}
```

Response: `contract: provisional-modelmatch-chat-v1`, `contract_verified: false`, `reply` (report text), `analysis_id`, `result`, and agent-attributed `tool_calls` as above. Task clarification/error status remains explicit within `result`. Transport/validation errors use FastAPI error responses. Replace the outer adapter when the authoritative course contract is supplied; preserve the inner trace records and research implementation.

## Execution and Cloud Run preparation

Production startup:

```sh
.venv/bin/uvicorn app:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1 --timeout-keep-alive 5
```

`python app.py` also honors `PORT` and binds 0.0.0.0. The Dockerfile uses the existing lockfile; building requires dependency/image downloads and has not been performed as part of offline verification. ADC must come from the runtime service account, never a key bundled into the image. `.dockerignore` and `.gcloudignore` exclude local secrets, caches, development docs and tests. Docker COPY lists the runtime source explicitly; no runtime or test dependency on `docs/` exists. Bundled `examples/offline-aa.json` is synthetic and used only when offline mode is explicitly selected.

Each analysis, including compatibility `/run`, uses the same service limits: 24 model generations, 30-second provider requests, 180-second workflow research, 190-second outer timeout, six researcher runs and one follow-up round. There are no configured provider retries. Two concurrent analyses and six starts/minute per process are allowed. POST input bodies are capped at 16000 bytes, question length at 6000 characters, and SSE queues at 512 events. Event overflow stops research. Health checks and deterministic recalculation do not consume provider quota.

Evidence sessions are **ephemeral, single-process memory**, retained for at most 30 minutes, eight sessions, and approximately 64 MiB of serialized saved content (not a guarantee on Python heap size). Results over 32 MiB are not retained for recalculation. Eviction/restart invalidates analysis IDs; IDs are unguessable bearer capabilities and should not be shared. Rate/concurrency limits are process-local. AA cache in `/tmp/modelmatch-aa` is an optimization; an empty cache can fetch the live API with AA_API_KEY. No session correctness relies on disk persistence.

Before Cloud Run production deployment: add authentication/access control, tenant-scoped shared evidence storage with TTL and encryption, distributed request budgets/rate limits, and authenticated trace access. Multiple instances/workers are unsupported for reliable recalculation until shared storage is added. Validate the container, set an HTTP timeout exceeding the bounded workflow, review concurrency, verify the runtime service account/Vertex permissions and AA secret injection, and verify the course contract. Do not expose this unauthenticated research endpoint publicly as-is. No IAM/API changes, billable tests, or deployment are automatic.
