# Snapshot-bound product family review

`tools/family_mapping.py` loads versioned, explicit model-ID mappings. The current
`aa-label-families-v2` enumerates 23 AA entries in 10 reviewed product-label groups.
`tools/family_mapping_reviewed.py` contains the additional per-ID identities and review
rationales. Version `aa-label-families-v1` remains reproducible via
`load_family_mapping(version="aa-label-families-v1")`; frozen sessions keep their original
manifest and do not reload the current default.

These mappings apply only to snapshot `eec442cab98cf613`, retrieved at
`2026-11-11T02:25:31.784289+00:00` from the
[AA Free API](https://artificialanalysis.ai/api/v2/language/models/free).
Exact creator ID, model ID, original name/slug, release date, source, retrieval time and
snapshot binding must match. Another snapshot stays unknown even if labels look identical.
The original 734-entry snapshot is local audit material and is not bundled or refreshed by
this module. `tests/fixtures/aa_family_identity_excerpt.json` retains identity-only source
excerpts for review regressions; it contains no benchmark scores and is not a usable live
snapshot or a replacement for the complete AA data.

## Explicit revalidation for the retained 757-entry snapshot

`aa-label-families-v3` is an independent identity-only manifest in
`tools/family_mapping_revalidated.py`, bound to snapshot `d83dcce1043c1044`, retrieved
at `2026-11-18T02:17:14.526737+00:00`. All 23 reviewed IDs, complete creator objects,
names, slugs and release dates matched the two retained sources exactly. Existing
product/version, size and routing boundaries were reviewed without adding any members.
The scope remains AA product labels, never provider-verified weight or routing equivalence.
The manifest retains source fingerprints and prior-review provenance but copies no
benchmark, pricing or performance metrics. The snapshots contain changed metric evidence;
only the current Decision's source evidence may be used for scoring.

`load_family_mapping(snapshot_id=...)` selects v3 only for this exact snapshot ID;
historical v1/v2 are unchanged and available explicitly. Other snapshots do not inherit
v3, even when all names match. The sidecar still checks source, retrieval time and exact
identity, and validates live snapshot content against its digest. Current snapshot
coverage is 23/757 entries across 10 curated product-label families; the remaining 734
entries stay unknown. Frozen sessions retain their full original manifest on recalculation.
`tests/fixtures/aa_revalidated_identity_excerpt.json` contains independent identity-only
source excerpts, not a substitute snapshot or real evaluation fixture.

## Meaning and boundaries

The existing `curated_aa_label` confidence means reviewed **product-family grouping**,
not verified identical weights, deployment equivalence, model quality, current availability,
or hosting/provider identity. No official provider documentation was fetched for this review.
AA label patterns propose candidates for review; runtime never assigns a family from a
similar name. Group relationships are explicit decisions over the enumerated source records.
Missing official equivalence, routing, quantization, Preview and size information remains
unknown. A singleton group is an explicitly reviewed exact product identity, not a license
to include any unreviewed relative.

Each record includes snapshot/creator/model IDs, family ID, unique configuration key,
release/version distinction, mapping version, review status and supporting source fields.
Reasoning configurations stay separate AA entries with unchanged scores and raw ranks.
Release dates and product versions are boundaries; Full size and Default Fallback labels
are retained only where explicit. Unknown labels are not interpreted as "none" or "default".
There is no automatic inclusion across versions, releases, sizes, Preview, quantization,
routing labels, creators or unreviewed configurations. Unknown families are never given
singleton identities just to fill recommendation slots.

## Ranking-driven scope

The review covers the union of Top 20 IDs from the supported Financial domain proxy and
previously available Engineering/Strategy reference profiles. A separate Legal index-only
reference is diagnostic; the original Legal task retains its 100k context hard constraint.
The current priority union remains 23 IDs. Similar unreviewed configurations outside this
union remain unknown. Mapping expansion cannot fix missing task-relevant U, unverifiable
hard constraints or an absent comparable workload.

A conservative five-task audit separates missing accepted task mappings from explicitly
conditional reference profiles. Coding/tool-calling/shopping do not automatically inherit
Engineering or Strategy U. Generic reference results are not live task replay evidence.
The source coding/agentic fields have no supported mapping in the current six-domain
contract; this phase does not add one or change the Selector/scoring policy.

Replay only an existing local snapshot:

```sh
.venv/bin/python -B -m scripts.family_mapping_audit \
  --snapshot .cache/aa/aa-free-snapshot.json \
  --output .cache/phase6b4/replay.json
```

The script has no model/API client, credential loader or refresh path. It compares v1/v2
against identical Decisions, reports exact-ID Top 10/20 frequencies separately for primary
and reference profiles, preserves full scores/evidence and fails if inputs are mutated.
Its generated report belongs in ignored local storage. Family counts are not success
criteria: inspect actual slot availability, missing reasons and cohort/eligibility too.

Run regressions with:

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -B -m unittest discover -s tests
.venv/bin/python -B -m scripts.submission_audit
git diff --check
```

Tests adapt source identity excerpts into explicit mock envelopes only to test joins and
binding controls; they do not create or validate real benchmark values. Deployment and
live recommendation acceptance require separate authorization and validation.
