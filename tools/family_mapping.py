"""Manually audited AA-label groups, not provider-verified model equivalence."""

from copy import deepcopy

LEGACY_MAPPING_VERSION = "aa-label-families-v1"
MAPPING_VERSION = "aa-label-families-v2"
REVALIDATED_MAPPING_VERSION = "aa-label-families-v3"
REVALIDATED_SNAPSHOT_ID = "d83dcce1043c1044"


def _legacy_mapping():
    """Return an isolated manifest; no name parsing or network discovery occurs."""
    creator = "f0aa413f-e8ae-4fcd-9c48-0e049f4f3128"
    # These five identities were inspected in the retained real AA snapshot.
    members = (
        ("593f2d23-247b-41c9-a679-cebd225f0a9a", "Max", "claude-fable-5-2"),
        ("76942526-cc96-46b0-bc27-29561c53ed70", "Xhigh", "claude-fable-5-2-xhigh"),
        ("fdc1913b-9497-45ef-83f7-17dae756f37e", "High", "claude-fable-5-2-high"),
        ("0c9b4e05-9259-42cc-b40e-d6acbbeaa7e8", "Medium", "claude-fable-5-2-medium"),
        ("cfc7acb1-d903-4858-9b6c-6c7776caf8f9", "Low", "claude-fable-5-2-low"),
    )
    records = []
    for model_id, label, slug in members:
        identity = {"name": f"Claude Fable 5.2 ({label}, Default Fallback)", "slug": slug,
                    "release_date": "2026-11-09", "creator_id": creator, "creator_name": "Anthropic"}
        records.append({"model_id": model_id, "family_id": "anthropic:claude-fable-5.2",
            "expected_identity": identity,
            "configuration": {"reasoning_label": label, "routing_label": "Default Fallback",
                              "verification_status": "aa_label_only"},
            "supporting_evidence": {"snapshot_id": "eec442cab98cf613", "data_mode": "live",
                "retrieved_at": "2026-11-11T02:25:31.784289+00:00",
                "source_url": "https://artificialanalysis.ai/api/v2/language/models/free",
                "source_fields": deepcopy(identity), "source_model_id": model_id,
                "basis": "Manual comparison of exact AA identities; shared version label, distinct configuration labels. "
                         "No inference of provider routing, supported API settings or identical underlying weights."}})
    return {"version": LEGACY_MAPPING_VERSION, "families": {
        "anthropic:claude-fable-5.2": {"label": "Claude Fable 5.2", "creator_id": creator,
            "grouping_confidence": "curated_aa_label", "provider_equivalence_status": "unknown"}},
        "records": records}


def load_family_mapping(*, version=None, snapshot_id=None):
    """Load an explicit reviewed version; frozen sessions never reload this manifest."""
    if version is None:
        version = REVALIDATED_MAPPING_VERSION if snapshot_id == REVALIDATED_SNAPSHOT_ID else MAPPING_VERSION
    if version == REVALIDATED_MAPPING_VERSION:
        from tools.family_mapping_revalidated import REVALIDATED_MAPPING
        return deepcopy(REVALIDATED_MAPPING)
    mapping = _legacy_mapping()
    if version == LEGACY_MAPPING_VERSION:
        return mapping
    if version != MAPPING_VERSION:
        raise ValueError("Unknown family mapping version.")
    from tools.family_mapping_reviewed import REVIEW_DATE, REVIEWED_GROUPS

    mapping["version"] = MAPPING_VERSION
    seed = mapping["families"]["anthropic:claude-fable-5.2"]
    seed.update(product_version="5.2", release_date="2026-11-09", size_label=None,
                routing_label="Default Fallback", review_status="reviewed_aa_product_label_only")
    for record in mapping["records"]:
        _annotate(record, "5.2", None, REVIEW_DATE)
    for group in REVIEWED_GROUPS:
        family = {key: deepcopy(group[key]) for key in ("label", "creator_id", "product_version", "release_date", "size_label", "routing_label")}
        family.update(grouping_confidence="curated_aa_label", provider_equivalence_status="unknown",
                      review_status="reviewed_aa_product_label_only", rationale=group["rationale"])
        mapping["families"][group["family_id"]] = family
        for member in group["members"]:
            identity = deepcopy(member["identity"])
            if identity["creator_id"] != group["creator_id"] or identity["release_date"] != group["release_date"]:
                raise ValueError("Reviewed product group crosses creator or release boundaries.")
            record = {"model_id": member["model_id"], "family_id": group["family_id"],
                "expected_identity": identity,
                "configuration": {"reasoning_label": member["reasoning_label"],
                                  "routing_label": group["routing_label"], "verification_status": "aa_label_only"},
                "supporting_evidence": {"snapshot_id": "eec442cab98cf613", "data_mode": "live",
                    "retrieved_at": "2026-11-11T02:25:31.784289+00:00",
                    "source_url": "https://artificialanalysis.ai/api/v2/language/models/free",
                    "source_model_id": member["model_id"], "source_fields": deepcopy(identity),
                    "basis": group["rationale"]}}
            _annotate(record, group["product_version"], group["size_label"], REVIEW_DATE)
            mapping["records"].append(record)
    mapping["records"].sort(key=lambda record: record["model_id"])
    return mapping


def _annotate(record, product_version, size_label, review_date):
    """Keep explicit review and configuration identity without equivalence claims."""
    record.update(snapshot_id=record["supporting_evidence"]["snapshot_id"],
                  creator_id=record["expected_identity"]["creator_id"],
                  configuration_key="aa-configuration:" + record["model_id"],
                  release_version={"product_version": product_version,
                                   "release_date": record["expected_identity"]["release_date"]},
                  review_status="reviewed_aa_product_label_only", mapping_version=MAPPING_VERSION)
    record["configuration"].update(configuration_key=record["configuration_key"], size_label=size_label,
        preview_label=None, quantization_label=None,
        unspecified_labels_status="unknown_not_inferred")
    record["supporting_evidence"]["review"] = {
        "review_date": review_date, "status": record["review_status"], "mapping_version": MAPPING_VERSION,
        "release_version": deepcopy(record["release_version"]),
        "scope": "Repository product-label curation from retained AA identity evidence; no official equivalence verification."}
