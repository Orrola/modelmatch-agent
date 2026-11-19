"""Snapshot-bound exact model identities; names are preserved without inference."""

import hashlib
import json

from tools.model_evidence import _snapshot_rows

METADATA_VERSION = "model-identity-v2"


def snapshot_binding(snapshot):
    """Reuse existing AA validation and bind even synthetic snapshots by content."""
    rows = _snapshot_rows(snapshot)
    fingerprint = hashlib.sha256(json.dumps(snapshot["pages"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    if snapshot["data_mode"] == "live" and snapshot["snapshot_id"] != fingerprint[:16]:
        raise ValueError("Live snapshot ID does not match its retained page digest.")
    return rows, {"snapshot_id": snapshot["snapshot_id"], "snapshot_fingerprint": fingerprint,
                  "data_mode": snapshot["data_mode"], "source_url": snapshot["source_url"],
                  "retrieved_at": snapshot.get("retrieved_at")}


def build_identity_sidecar(snapshot):
    """Preserve exact source identities without grouping or inferred configuration."""
    rows, binding = snapshot_binding(snapshot)
    models = {}
    for model_id, (row, _) in sorted(rows.items()):
        creator = row.get("model_creator") if isinstance(row.get("model_creator"), dict) else {}
        models[model_id] = {"model_id": model_id, "snapshot_id": binding["snapshot_id"],
            "original_name": row.get("name"), "original_slug": row.get("slug"),
            "release_date": row.get("release_date"), "creator_id": creator.get("id"),
            "creator_name": creator.get("name"), "provider": None, "provider_status": "unknown",
            "identity_status": "synthetic_fixture" if binding["data_mode"] == "mock" else "aa_observed"}
    return {"metadata_version": METADATA_VERSION, **binding, "models": models,
            "coverage": {"total": len(models),
                "creator_identified": sum(bool(m["creator_id"] and m["creator_name"]) for m in models.values())}}
