"""
Deterministic bridge between Agent3-V5.2 verification output
and Agent4-V3 verified_evidence_package input.

This module does NOT modify Agent3 verification decisions. It only
restores request-side scene identity and original atomic claim text that
are required by Agent4-V3.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


GROUPS = (
    "accepted_claims",
    "revised_claims",
    "rejected_claims",
    "pending_claims",
)


def enrich_verified_package(
    package: dict[str, Any],
    *,
    sample_id: str,
    claim_list: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(package, dict):
        raise TypeError("package must be a dict")

    if not isinstance(claim_list, list):
        raise TypeError("claim_list must be a list")

    sample_id = str(sample_id or "").strip()
    if not sample_id:
        raise ValueError("sample_id must not be empty")

    claim_index: dict[str, dict[str, Any]] = {}

    for claim in claim_list:
        if not isinstance(claim, dict):
            raise TypeError("claim_list items must be dicts")

        claim_id = str(claim.get("claim_id", "")).strip()
        claim_text = str(
            claim.get("claim", claim.get("atomic_claim", ""))
        ).strip()

        if not claim_id:
            raise ValueError("claim_id must not be empty")
        if not claim_text:
            raise ValueError(f"claim {claim_id} has no text")
        if claim_id in claim_index:
            raise ValueError(f"duplicate claim_id: {claim_id}")

        claim_index[claim_id] = {
            **claim,
            "claim_id": claim_id,
            "claim": claim_text,
        }

    result = deepcopy(package)

    # Force the enriched contract version instead of leaving a historical
    # Agent3 package version in place.
    result["schema_version"] = "agent3_verified_package_v1.1"

    task_info = result.get("task_info")
    if not isinstance(task_info, dict):
        task_info = {}
        result["task_info"] = task_info
    task_info["scene_uid"] = sample_id

    for group in GROUPS:
        items = result.setdefault(group, [])
        if not isinstance(items, list):
            raise TypeError(f"{group} must be a list")

        for item in items:
            if not isinstance(item, dict):
                raise TypeError(f"{group} items must be dicts")

            claim_id = str(item.get("claim_id", "")).strip()
            source = claim_index.get(claim_id)
            if source is None:
                raise ValueError(
                    "verified package references unknown claim_id: "
                    f"{claim_id}"
                )

            atomic_claim = source["claim"]
            item["atomic_claim"] = atomic_claim

            if not item.get("claim_type") and source.get("claim_type"):
                item["claim_type"] = source["claim_type"]

            # Agent4-V3 consumes report_text/suggested_revision/atomic_claim
            # in that order. Accepted claims use the original verified text;
            # revised claims prefer the verifier's safe revision.
            if group == "accepted_claims":
                item["report_text"] = atomic_claim
            elif group == "revised_claims":
                revision = str(item.get("suggested_revision", "")).strip()
                item["report_text"] = revision or atomic_claim

    result["summary"] = {
        "accepted": len(result["accepted_claims"]),
        "revised": len(result["revised_claims"]),
        "rejected": len(result["rejected_claims"]),
        "pending": len(result["pending_claims"]),
    }

    return result
