"""Deterministically link Agent2 claims to normalized Agent1 evidence."""

from __future__ import annotations

from typing import Any


EVIDENCE_LINKER_VERSION = "claim-type-evidence-rules-v1"

BUILDING_TYPES = {
    "building_damage_level",
    "building_damage_presence",
    "building_damage_quantity",
}
ROAD_TYPES = {"road_displacement", "road_impact"}


def _first_available(candidates: list[str], known: set[str]) -> list[str]:
    return [item for item in candidates if item in known]


def _building_instance_ids(evidence_list: list[dict[str, Any]]) -> list[str]:
    damaged: list[str] = []
    other: list[str] = []
    for item in evidence_list:
        if item.get("evidence_type") != "building_instance":
            continue
        evidence_id = str(item.get("evidence_id") or "")
        statistics = item.get("supporting_statistics")
        statistics = statistics if isinstance(statistics, dict) else {}
        (damaged if statistics.get("is_damaged") else other).append(evidence_id)
    return sorted(damaged) + sorted(other)


def _default_links(
    claim_type: str,
    *,
    known: set[str],
    building_ids: list[str],
    max_building_instances: int,
) -> list[str]:
    if claim_type == "building_damage_quantity":
        candidates = [
            "SCENE_BUILDING_SUMMARY",
            "VIS_PRE_POST",
            "VIS_DAMAGE_MAP",
            "VIS_FUSED_OVERLAY",
        ]
    elif claim_type in {"building_damage_level", "building_damage_presence"}:
        candidates = [
            "SCENE_BUILDING_SUMMARY",
            *building_ids[:max_building_instances],
            "VIS_PRE_POST",
            "VIS_DAMAGE_MAP",
            "VIS_BUILDING_INSTANCE_MASK",
            "VIS_FUSED_OVERLAY",
        ]
    elif claim_type in ROAD_TYPES:
        candidates = [
            "R0001",
            "VIS_PRE_POST",
            "VIS_ROAD_STATUS_MAP",
            "VIS_FUSED_OVERLAY",
        ]
    elif claim_type == "disaster_type_inference":
        candidates = [
            "SCENE_BUILDING_SUMMARY",
            "R0001",
            "VIS_PRE_POST",
            "VIS_DAMAGE_MAP",
            "VIS_ROAD_STATUS_MAP",
            "VIS_FUSED_OVERLAY",
        ]
    else:
        candidates = ["VIS_PRE_POST", "VIS_FUSED_OVERLAY"]
    return _first_available(candidates, known)


def link_claims_to_evidence(
    claim_list: list[dict[str, Any]],
    evidence_list: list[dict[str, Any]],
    *,
    max_building_instances: int = 8,
) -> list[dict[str, Any]]:
    """Copy claims and attach only evidence IDs present in ``evidence_list``."""

    if max_building_instances < 0:
        raise ValueError("max_building_instances must be non-negative")
    known = {
        str(item.get("evidence_id") or "").strip()
        for item in evidence_list
        if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
    }
    if not known:
        raise ValueError("evidence_list does not contain usable evidence IDs")
    building_ids = _building_instance_ids(evidence_list)

    result: list[dict[str, Any]] = []
    for source in claim_list:
        if not isinstance(source, dict):
            raise TypeError("claim_list items must be objects")
        claim = dict(source)
        claim_type = str(claim.get("claim_type") or "").strip()
        explicit = claim.get("related_evidence_ids") or []
        if not isinstance(explicit, list) or not all(
            isinstance(item, str) for item in explicit
        ):
            raise ValueError("related_evidence_ids must be a string list")
        unknown = sorted(set(explicit) - known)
        if unknown:
            raise ValueError(
                "claim references unknown evidence IDs: " + ", ".join(unknown)
            )

        defaults = _default_links(
            claim_type,
            known=known,
            building_ids=building_ids,
            max_building_instances=max_building_instances,
        )
        links = list(dict.fromkeys([*explicit, *defaults]))
        if not links:
            raise ValueError(
                f"no compatible evidence is available for claim {claim.get('claim_id')}"
            )
        claim["related_evidence_ids"] = links
        claim["evidence_linker_version"] = EVIDENCE_LINKER_VERSION
        result.append(claim)
    return result
