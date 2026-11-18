"""Snapshot-bound model identities; audited grouping never normalizes model names."""

import hashlib
import json
from copy import deepcopy

from tools.family_mapping import load_family_mapping
from tools.model_evidence import _snapshot_rows

METADATA_VERSION = "model-identity-v1"


def snapshot_binding(snapshot):
    """Reuse existing AA validation and bind even synthetic snapshots by content."""
    rows = _snapshot_rows(snapshot)
    fingerprint = hashlib.sha256(json.dumps(snapshot["pages"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    if snapshot["data_mode"] == "live" and snapshot["snapshot_id"] != fingerprint[:16]:
        raise ValueError("Live snapshot ID does not match its retained page digest.")
    return rows, {"snapshot_id": snapshot["snapshot_id"], "snapshot_fingerprint": fingerprint,
                  "data_mode": snapshot["data_mode"], "source_url": snapshot["source_url"],
                  "retrieved_at": snapshot.get("retrieved_at")}


def _validated_mapping(mapping):
    if not isinstance(mapping.get("version"), str) or not mapping["version"].strip():
        raise ValueError("Family mapping requires an explicit version.")
    records = {}
    for record in mapping["records"]:
        model_id = record["model_id"]
        if not isinstance(model_id, str) or not model_id or model_id in records:
            raise ValueError("Family mapping contains an invalid or conflicting model ID.")
        family = mapping["families"].get(record["family_id"])
        identity, source = record["expected_identity"], record["supporting_evidence"]
        if not family or family["creator_id"] != identity["creator_id"]:
            raise ValueError("Family mapping cannot merge different creators.")
        if (source["source_model_id"] != model_id or source["source_fields"] != identity
                or not source["source_url"] or not source["basis"] or not source["snapshot_id"]):
            raise ValueError("Family mapping requires matching supporting identity evidence.")
        if family["grouping_confidence"] != "curated_aa_label" or family["provider_equivalence_status"] != "unknown":
            raise ValueError("This mapping cannot establish provider-verified equivalence.")
        records[model_id] = record
    return records


def build_identity_sidecar(snapshot, *, mapping=None):
    """Preserve every exact identity, with independent source and grouping status."""
    rows, binding = snapshot_binding(snapshot)
    mapping = deepcopy(load_family_mapping(snapshot_id=binding["snapshot_id"]) if mapping is None else mapping)
    records = _validated_mapping(mapping)
    models = {}
    for model_id, (row, _) in sorted(rows.items()):
        creator = row.get("model_creator") if isinstance(row.get("model_creator"), dict) else {}
        identity = {"name": row.get("name"), "slug": row.get("slug"), "release_date": row.get("release_date"),
                    "creator_id": creator.get("id"), "creator_name": creator.get("name")}
        family_id, family, configuration, support = None, None, None, None
        status = "unknown_unmapped"
        if model_id in records:
            record = records[model_id]
            source = record["supporting_evidence"]
            if any(source[k] != binding[k] for k in ("snapshot_id", "data_mode", "source_url", "retrieved_at")):
                status = "unknown_mapping_snapshot_mismatch"
            elif record["expected_identity"] != identity:
                status = "unknown_identity_mismatch"
            else:
                status = "curated_aa_label"
                family_id = record["family_id"]
                family = deepcopy(mapping["families"][family_id])
                configuration = deepcopy(record["configuration"])
                support = deepcopy(source)
        models[model_id] = {"model_id": model_id, "snapshot_id": binding["snapshot_id"],
            "original_name": identity["name"], "original_slug": identity["slug"],
            "release_date": identity["release_date"], "creator_id": identity["creator_id"],
            "creator_name": identity["creator_name"], "provider": None, "provider_status": "unknown",
            "family_id": family_id, "family": family, "family_status": status,
            "configuration": configuration, "supporting_evidence": support,
            "identity_status": "synthetic_fixture" if binding["data_mode"] == "mock" else "aa_observed",
            "mapping_version": mapping["version"]}
    return {"metadata_version": METADATA_VERSION, "mapping_version": mapping["version"], **binding,
            "models": models, "coverage": {
                "total": len(models),
                "creator_identified": sum(bool(m["creator_id"] and m["creator_name"]) for m in models.values()),
                "curated_family_entries": sum(m["family_id"] is not None for m in models.values()),
                "curated_families": len({m["family_id"] for m in models.values() if m["family_id"]}),
                "unknown_family_entries": sum(m["family_id"] is None for m in models.values())}}
