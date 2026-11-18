"""Local Selector integration with frozen inputs and independently safe failure states."""

from copy import deepcopy

from tools.evidence_coverage import COVERAGE_VERSION, analyze_evidence_coverage
from tools.family_mapping import load_family_mapping
from tools.model_metadata import METADATA_VERSION, build_identity_sidecar
from tools.recommendation_selector import SELECTOR_VERSION, select_recommendations
from tools.run_diagnostics import failure_details


class SelectionContextError(ValueError):
    """Stable local context failure; no raw data is included in diagnostics."""


def identity_presentation(metadata):
    """Expose existing validated identities and membership, never infer new groups."""
    models, families = {}, {}
    for mid, model in sorted(metadata["models"].items()):
        models[mid] = {key: deepcopy(model[key]) for key in (
            "model_id", "original_name", "original_slug", "release_date", "creator_id", "creator_name",
            "family_id", "family_status", "configuration", "provider", "provider_status")}
        family = model["family"]
        if model["family_status"] == "curated_aa_label" and family and model["family_id"]:
            entry = families.setdefault(model["family_id"], {"label": family["label"], "model_ids": [],
                "status": "curated_aa_label", "provider_equivalence_status": "unknown"})
            entry["model_ids"].append(mid)
    return {**{key: metadata[key] for key in ("snapshot_id", "snapshot_fingerprint", "data_mode", "retrieved_at",
        "source_url", "mapping_version", "metadata_version")}, "models": models, "families": families}


def selection_for_decision(decision, prepared, *, snapshot=None, frozen_context=None):
    """Return additive public fields and a private context, without network calls."""
    context = frozen_context
    phase = "metadata"
    try:
        if context is None:
            if snapshot is None:
                raise SelectionContextError("Frozen Selector context is unavailable.")
            bound = {k: deepcopy(snapshot[k]) for k in ("snapshot_id", "data_mode", "source_url", "retrieved_at", "pages")}
            mapping = load_family_mapping(snapshot_id=bound["snapshot_id"])
            metadata = build_identity_sidecar(bound, mapping=mapping)
            context = {"snapshot": bound, "metadata": metadata, "family_mapping": deepcopy(mapping),
                "selector_version": SELECTOR_VERSION, "metadata_version": METADATA_VERSION,
                "coverage_version": COVERAGE_VERSION, "decision_policy_version": decision["policy_version"]}
        if (context["selector_version"] != SELECTOR_VERSION or context["metadata_version"] != METADATA_VERSION
                or context["coverage_version"] != COVERAGE_VERSION
                or context["decision_policy_version"] != decision["policy_version"]):
            raise SelectionContextError("Frozen Selector versions are incompatible.")
        expected = build_identity_sidecar(context["snapshot"], mapping=context["family_mapping"])
        if expected != context["metadata"]:
            raise SelectionContextError("Frozen family mapping or metadata has changed.")
        phase = "coverage"
        coverage = analyze_evidence_coverage(context["snapshot"], prepared, context["metadata"], decision)
        phase = "selection"
        selection = select_recommendations(decision, context["metadata"], coverage)
        phase = "canonical_contract"
        from recommendation import writer_payload
        writer_payload(decision, selection)
        status = "limited_metadata" if context["metadata"]["coverage"]["unknown_family_entries"] else "available"
        return {"selection": selection, "model_identity": identity_presentation(context["metadata"]), "selector": {"status": status, "error": None,
            "metadata_coverage": deepcopy(context["metadata"]["coverage"]),
            "selector_version": SELECTOR_VERSION, "mapping_version": context["metadata"]["mapping_version"]}}, context
    except Exception as error:
        code = "selector_context_incompatible" if isinstance(error, SelectionContextError) else "selector_execution_failed"
        return {"selection": None, "model_identity": None, "selector": {"status": "unavailable",
            "error": {"code": code, "phase": phase, **failure_details(error)}, "selector_version": SELECTOR_VERSION}}, context
