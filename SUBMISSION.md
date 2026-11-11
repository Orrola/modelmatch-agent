# Submission readiness and evidence boundaries

No formal Project 2 assignment handout, grading rubric, or authoritative submission schema was found in this repository or the available local course material inspected during cleanup. Internal product notes are not an authoritative course rubric. Do not claim complete rubric compliance from them.

| Item | Evidence / remaining work |
|---|---|
| OpenAI Agents SDK and Agent-as-a-Tool | Implemented; Lead research tools launch independent Runner contexts |
| Parallel researchers | Offline barrier/overlap tests; bounded previous live pipeline observation; not every live branch is verified |
| Same Lead and iterative review | Implemented and tested offline with a one-round follow-up limit; targeted follow-up live coverage remains incomplete |
| Citations and evidence provenance | Exact AA IDs, snapshot/version/time, evidence IDs and missing manifests; official specs require separate verification |
| `/chat` | Provisional contract; a local previous Project 1 app has different response/session fields. Obtain the authoritative Project 2 contract before claiming compatibility |
| Cloud Run | Docker/PORT/non-root startup prepared; no deployment or public service availability is claimed |
| Live Writer | Reported failure unresolved; writer_rejected/writer_fallback must remain visible and cannot count as live success |
| Baseline comparisons, evaluation deliverables, slides or video | Exact course requirements unavailable; not claimed complete |
| Final `submission.json` | Missing: confirmed author list, deployed URL and authoritative schema. `submission.example.json` is an incomplete example, not a valid final submission |
| Service availability through grading | Not established; no deployed URL exists in this repository |

The internal PRD suggests a final manifest with `deploy_url`, `authors`, and `path: "research"`. The previous Project 1 submission contains deploy_url/authors, but does not establish the Project 2 schema. Populate the actual final manifest only after confirming the instructions and author list and obtaining a tested deployment URL. No authors or URLs are invented here.

Before final submission:

1. Obtain the official assignment/rubric and reconcile the exact `/chat` contract and deliverable list.
2. Diagnose and validate the reported live Writer failure under a separately authorized request budget.
3. Verify the container and runtime identity, AA secret injection, and application health on the target platform.
4. Complete authentication/shared-state requirements appropriate to the intended deployment.
5. Fill and validate the actual submission manifest; include every confirmed author.
6. Run offline regression and `python -m scripts.submission_audit`, inspect the actual staged files, then perform any separately approved live/deployment validation.

Internal development `docs/` and `.cache/` are intentionally excluded. Runtime and tests must work without them. Do not commit credentials or redistribute real AA snapshots without checking applicable data terms. The audit script never stages, commits, pushes, untracks, deploys or prints matched secret values.
