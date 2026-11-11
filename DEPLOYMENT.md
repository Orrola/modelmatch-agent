# Deployment readiness

This is an operating plan, not a deployment record. No cloud resources or permissions are created by these instructions. The source is locally testable; the image, cloud identity, provider access and complete live product are not yet accepted for production. The reported live Writer failure remains unresolved. A response with `writer_fallback=true` is not successful live Writer validation.

## Build and startup

```sh
uv sync --locked
MODELMATCH_OFFLINE=0 GOOGLE_CLOUD_PROJECT=ieor4570-yg3133 GOOGLE_CLOUD_LOCATION=global \
  .venv/bin/uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --timeout-keep-alive 5
```

Open `/modelmatch`. Startup, static assets, `/api/modelmatch/config` and `/healthz` do not contact providers. Health means process health only. An analysis starts after an explicit request; failed live dependencies never select synthetic results. Grounding is disabled in the web workflow.

The Dockerfile uses Python 3.13, pinned uv 0.12.12 and `uv sync --locked --no-dev`; interpreter downloads are disabled. Dependency versions come from `uv.lock`. The Python base tag is not digest-pinned: record and approve an image digest before a reproducible release. Registry availability and Linux dependency installation have not been verified locally. A successful local uv check is not an image build.

On a machine with Docker, run these non-provider checks before deployment:

```sh
docker build -t modelmatch-ai .
docker run --rm --name modelmatch-readiness -p 8080:8080 -e PORT=8080 -e MODELMATCH_OFFLINE=0 modelmatch-ai
# In another terminal:
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/api/modelmatch/config
curl --fail --output /dev/null http://127.0.0.1:8080/modelmatch
```

These commands need no credentials because they do not initiate an analysis. Test a non-default PORT as well. Inspect the built image for excluded artifacts and verify non-root execution. Both upload/build ignore files use explicit runtime allowlists; no `.env`, ADC, internal documentation, tests or caches should enter the image. The labeled synthetic example remains bundled for explicit tests only; production must retain `MODELMATCH_OFFLINE=0`. Do not use `--env-file .env` as a production secret strategy.

## Runtime configuration and identity

| Setting | Production requirement |
|---|---|
| `MODELMATCH_OFFLINE` | `0`; do not override with `1` in production |
| `GOOGLE_CLOUD_PROJECT` | `ieor4570-yg3133`, explicit; do not rely on gcloud in the container |
| `GOOGLE_CLOUD_LOCATION` | Existing configured `global`; manually verify model availability |
| `MODELMATCH_VERTEX_MODEL` | Current `gemini-3.5-flash` for Lead/Writer |
| `MODELMATCH_RESEARCHER_MODEL` | Current `gemini-3.5-flash-lite` |
| `AA_API_KEY` | Server-side secret injection, preferably a pinned Secret Manager version |
| `MODELMATCH_CACHE_DIR` | Writable disposable `/tmp/modelmatch-aa`; no volume required |
| `PORT` | Platform-provided; server binds `0.0.0.0` and one worker |

Attach a dedicated runtime service account. Google auth must obtain ADC from the runtime identity, not local user ADC or a downloaded service-account key. Do not set `GOOGLE_APPLICATION_CREDENTIALS` to a developer path. The container does not include gcloud. Do not set a Gemini API key merely to replace working Vertex ADC.

Manually verify these prerequisites against current Google Cloud policy before provisioning or deployment; they have not been checked by cloud API calls in this phase:

- Runtime identity: Vertex prediction access, typically `roles/aiplatform.user`; confirm the least permissions needed by the selected publisher models, including `aiplatform.endpoints.predict`. Verify `serviceusage.services.use` where required; grant a consumer role only if necessary.
- AA secret: `roles/secretmanager.secretAccessor` on the individual AA secret, not all project secrets. Avoid storing a literal key in deployment commands or shell history.
- Vertex AI API (`aiplatform.googleapis.com`), Cloud Run API (`run.googleapis.com`), and Artifact Registry API (`artifactregistry.googleapis.com`) for the chosen build/deploy flow. Secret Manager API (`secretmanager.googleapis.com`) if using secrets; Cloud Build API (`cloudbuild.googleapis.com`) only if that build service is chosen.
- Deployer/build identities: sufficient scoped Run deployment, service-account act-as, image push/pull and build permissions for the chosen flow. Keep these separate from runtime privileges. Do not grant Owner/Editor to solve a deployment error.
- Existing project billing, model entitlement, regional availability and quotas; no assumption that a model ID available locally remains available on the target endpoint.

Nothing here enables services, modifies IAM, creates secrets or confirms permissions. Validate without printing access tokens, credential files or AA key values.

## Sessions, concurrency and cancellation

The current application has one process-local `AnalysisService`. Each analysis creates its own SDK workflow, Lead history, independent researcher contexts and snapshot. A/B/C share that analysis snapshot; models and request budgets are not reused across users. Session IDs are random bearer capabilities, not authenticated ownership records.

- Recalculation uses saved prepared evidence in memory: 30-minute expiry, at most eight entries and approximately 64 MiB serialized total; entries over 32 MiB are not saved. Actual Python heap usage can be larger. Expiry is checked on access/write, not by a continuous cleanup worker.
- Restart, eviction or instance routing can invalidate an ID; the API returns an explicit error. Session affinity is not durability. Multiple workers/instances cannot provide reliable recalculation with this implementation.
- Two concurrent analyses and six starts/minute are enforced per process. These are burst bounds, not a daily spending cap. Locks are not distributed. The acquisition path contains no await before counters change on the single event loop.
- AA cache is an optimization, not session storage. Empty storage fetches real AA data only during an analysis. Concurrent cache misses may duplicate bounded AA requests; atomic file replacement prevents partial cache writes. Cloud Run temporary files are disposable and contribute to memory use.
- SSE keeps the HTTP request open, sends heartbeat comments, and has no reconnect/replay. Disconnect cancels the associated task and releases the slot; provider requests already sent may still finish and incur usage. A timed-out worker thread may also finish its local configuration work later. There is no durable background job queue or supported continuation after HTTP completion.

For a restricted initial pilot, recommend one worker, max instances 1, min instances 0, container concurrency 4, HTTP timeout 240 seconds, 1 CPU and 2 GiB memory. These are conservative starting recommendations, not measured capacity or guaranteed platform limits. Four request slots allow two analyses plus utility/recalculation traffic; application admission still caps analyses at two. Verify memory, CPU and SSE behavior under load. A single instance still restarts and loses sessions; users must accept that limitation explicitly. Do not treat it as distributed-session support.

If sessions must survive restarts/scaling, the smallest future storage adaptation is a private shared object store for immutable serialized prepared evidence/results, with server-enforced expiry and authenticated ownership checks; a Cloud Storage bucket is one option. Lifecycle cleanup alone does not enforce exact expiry. This adds IAM, retention, latency and data-handling decisions. Redis or database-backed metadata are alternatives, not required resources already provisioned. Large evidence objects require size-aware storage design. Do not add infrastructure until its requirements and cost are approved.

## Access control and cost safety

**Do not expose the current analysis endpoints anonymously.** `approve_live=true` is consent in a request body, not authentication; it is trivial for a remote client to supply. The same-origin POST check is not an authorization boundary. Compatibility `GET /run` also starts paid work and must be protected. Protect `/chat`, analysis, recalculation and traces together.

For the first limited pilot, prefer IAM-authenticated Cloud Run with invoker access granted only to the owner/evaluators and a verified authenticated browser access path, such as an approved authenticated proxy or IAP configuration. A private Cloud Run URL does not itself provide an interactive browser sign-in flow. Verify the chosen method against evaluator access needs before deploying. If the course requires a public page, choose a separately authenticated, quota-bounded analysis gateway; a public landing page must not expose anonymous paid analysis. Neither gateway nor IAP has been implemented/provisioned here. Do not enable unauthenticated invocation to work around evaluator access issues.

Current per-analysis limits: 24 Gemini generations, 2048 configured output tokens each, 30-second provider deadlines, zero model retries, 180-second workflow / 190-second outer deadline, at most six researcher runs including one targeted follow-up round. The nominal sum of configured output allowances is 49,152 tokens, not an observed usage total, monetary estimate or guaranteed bound on thinking-token billing. AA uses its own bounded pagination (default at most 10 pages), 30-second HTTP timeout, at most two retries per page and capped retry waits. The workflow deadline can end acquisition earlier. No candidate-model benchmarking or web Grounding is enabled.

Before any broader access, establish per-principal/daily quotas or an externally enforced bounded evaluation window and a kill switch. One instance plus burst limits does not prevent sustained spending; billing alerts alone are not a hard cutoff. Do not claim a dollar cap from generation limits. Actual cost requires billing evidence.

Keep application/ASGI access logs free of request bodies, credentials and raw prompts. `/run` places the question in a URL and may therefore expose it in access logs: avoid it for sensitive input and review platform logging/redaction before enabling it. Prefer the normal POST UI endpoint. Existing sanitized tool traces contain bounded excerpts of user/evidence content and must be restricted to authorized users. Platform logs, retention and redaction require cloud review; Python sanitization alone does not prove platform logs are safe.

## Release gates

1. Obtain authoritative Project 2 rubric, `/chat` contract and final submission requirements. Current adapter is explicitly provisional; Project 1 is not proof of Project 2 compatibility.
2. Build/run the image and check non-default PORT, assets, non-root identity and exclusion rules.
3. Confirm runtime IAM, APIs, model availability and AA secret injection with separately authorized checks.
4. Approve and verify authenticated evaluator access and spending controls; explicitly accept single-instance session loss or approve shared storage work.
5. Diagnose the reported Writer failure in a separately authorized bounded live test; preserve `writer_rejected`/`writer_fallback` meanwhile. Grounding specifications remain unknown without accepted evidence.
6. Authorize deployment and live acceptance separately; verify actual SSE behavior, provider usage, recommendations and permissions before claiming a fully validated service.
7. Complete the verified author list, deployed URL and actual submission manifest. Never commit credentials, internal records or fabricated verification claims.
