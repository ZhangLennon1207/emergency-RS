"""Convert Agent1's nested evidence ledger to the Agent3 HTTP evidence list."""

from __future__ import annotations

import math
from typing import Any, Iterable


EVIDENCE_MAPPER_VERSION = "agent1-ledger-2.1-to-evidence-list-v1"

VISUAL_EVIDENCE = {
    "input_pre_post": {
        "evidence_id": "VIS_PRE_POST",
        "evidence_type": "paired_original_imagery",
        "finding": "Paired pre-disaster and post-disaster imagery is available.",
    },
    "damage_instance_color": {
        "evidence_id": "VIS_DAMAGE_MAP",
        "evidence_type": "building_damage_map",
        "finding": "Agent1 building-damage visualization is available.",
    },
    "fused_overlay": {
        "evidence_id": "VIS_FUSED_OVERLAY",
        "evidence_type": "fused_overlay",
        "finding": "Agent1 fused visual overlay is available.",
    },
    "road_status_color": {
        "evidence_id": "VIS_ROAD_STATUS_MAP",
        "evidence_type": "road_status_map",
        "finding": "Agent1 road-status visualization is available.",
    },
    "building_instance_mask": {
        "evidence_id": "VIS_BUILDING_INSTANCE_MASK",
        "evidence_type": "building_instance_mask",
        "finding": "Agent1 building-instance localization mask is available.",
    },
}


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Agent1 ledger {name} must be an object")
    return value


def _confidence(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0.0 <= number <= 1.0 else None


def _bbox(value: Any) -> dict[str, int] | list[int] | None:
    if isinstance(value, dict):
        keys = ("x_min", "y_min", "x_max", "y_max")
        if all(isinstance(value.get(key), int) for key in keys):
            return {key: int(value[key]) for key in keys}
    if (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
    ):
        return [int(item) for item in value]
    return None


def _visual_items(available_artifact_types: Iterable[str]) -> list[dict[str, Any]]:
    available = {str(item) for item in available_artifact_types}
    available.add("input_pre_post")
    result = []
    for artifact_type, template in VISUAL_EVIDENCE.items():
        if artifact_type not in available:
            continue
        result.append(
            {
                **template,
                "source_agent": "agent1",
                "supporting_statistics": {},
                "confidence": None,
                "confidence_is_calibrated": False,
            }
        )
    return result


def build_evidence_list(
    ledger: dict[str, Any],
    *,
    available_artifact_types: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Flatten one Agent1 schema-2.1 ledger without inventing model facts."""

    if not isinstance(ledger, dict):
        raise TypeError("Agent1 evidence ledger must be an object")
    building = _object(ledger.get("building_evidence"), "building_evidence")
    road = _object(ledger.get("road_evidence"), "road_evidence")
    assessment = ledger.get("derived_assessment")
    assessment = assessment if isinstance(assessment, dict) else {}

    evidence: list[dict[str, Any]] = _visual_items(available_artifact_types)

    instances = building.get("building_instances")
    if not isinstance(instances, list):
        instances = []
    building_statistics = {
        key: value
        for key, value in building.items()
        if key != "building_instances"
    }
    building_statistics["building_risk_level"] = assessment.get(
        "building_risk_level"
    )
    building_statistics["scene_risk_level"] = assessment.get("scene_risk_level")
    evidence.append(
        {
            "evidence_id": "SCENE_BUILDING_SUMMARY",
            "source_agent": "agent1",
            "evidence_type": "building_scene_summary",
            "finding": "Agent1 scene-level building statistics.",
            "supporting_statistics": building_statistics,
            "confidence": None,
            "confidence_is_calibrated": False,
        }
    )

    for instance in instances:
        if not isinstance(instance, dict):
            continue
        evidence_id = str(instance.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        damaged = bool(instance.get("is_damaged"))
        damage_level = str(instance.get("damage_level") or "unknown")
        evidence.append(
            {
                "evidence_id": evidence_id,
                "source_agent": "agent1",
                "evidence_type": "building_instance",
                "finding": (
                    f"Building instance is classified as {damage_level} damage."
                    if damaged
                    else "Building instance is classified as not damaged."
                ),
                "supporting_statistics": {
                    key: value
                    for key, value in instance.items()
                    if key not in {"evidence_id", "bbox"}
                },
                "confidence": _confidence(
                    instance.get("damage_presence_confidence")
                ),
                "confidence_is_calibrated": bool(
                    instance.get("confidence_is_calibrated", False)
                ),
                "bbox": _bbox(instance.get("bbox")),
            }
        )

    road_id = str(road.get("evidence_id") or "R0001").strip()
    evidence.append(
        {
            "evidence_id": road_id,
            "source_agent": "agent1",
            "evidence_type": "road_scene_summary",
            "finding": (
                "Agent1 detects affected road pixels in the scene."
                if bool(road.get("is_affected"))
                else "Agent1 does not detect affected road pixels in the scene."
            ),
            "supporting_statistics": {
                **{key: value for key, value in road.items() if key not in {"evidence_id", "bbox"}},
                "road_risk_level": assessment.get("road_impact_level"),
                "scene_risk_level": assessment.get("scene_risk_level"),
            },
            "confidence": _confidence(road.get("affected_presence_confidence")),
            "confidence_is_calibrated": bool(
                road.get("confidence_is_calibrated", False)
            ),
            "bbox": _bbox(road.get("bbox")),
        }
    )

    identifiers = [item["evidence_id"] for item in evidence]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Agent1 evidence mapping produced duplicate evidence IDs")
    return evidence
