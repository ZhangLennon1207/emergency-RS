from __future__ import annotations

import pytest

from backend.app.integration import (
    add_claim_types,
    build_agent3_verify_payload,
    build_evidence_list,
    infer_claim_type,
    link_claims_to_evidence,
)


def sample_ledger():
    return {
        "schema_version": "2.1",
        "building_evidence": {
            "total_buildings": 2,
            "damaged_buildings": 1,
            "damage_ratio": 0.5,
            "damage_distribution": {"major_damage": 1, "no_damage": 1},
            "building_instances": [
                {
                    "evidence_id": "B0001",
                    "building_id": 1,
                    "bbox": {"x_min": 10, "y_min": 20, "x_max": 40, "y_max": 60},
                    "is_damaged": True,
                    "damage_level": "major_damage",
                    "damage_presence_confidence": 0.82,
                    "confidence_is_calibrated": False,
                },
                {
                    "evidence_id": "B0002",
                    "building_id": 2,
                    "bbox": {"x_min": 50, "y_min": 20, "x_max": 80, "y_max": 60},
                    "is_damaged": False,
                    "damage_level": "no_damage",
                    "damage_presence_confidence": 0.91,
                    "confidence_is_calibrated": False,
                },
            ],
        },
        "road_evidence": {
            "evidence_id": "R0001",
            "total_road_pixels": 100,
            "affected_road_pixels": 25,
            "affected_road_ratio": 0.25,
            "is_affected": True,
            "affected_presence_confidence": 0.73,
            "confidence_is_calibrated": False,
        },
        "derived_assessment": {
            "building_risk_level": "medium",
            "road_impact_level": "low",
            "scene_risk_level": "medium",
        },
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Several buildings appear damaged.", "building_damage_quantity"),
        ("A building shows severe structural damage.", "building_damage_level"),
        ("The main road appears blocked.", "road_impact"),
        ("The roadway is visibly displaced.", "road_displacement"),
        ("Floodwater expanded across the scene.", "water_change"),
        ("Vegetation cover visibly decreased.", "vegetation_change"),
    ],
)
def test_claim_type_rules(text, expected):
    assert infer_claim_type(text) == expected


def test_agent1_ledger_maps_to_flat_evidence_and_claim_links():
    evidence = build_evidence_list(
        sample_ledger(),
        available_artifact_types={
            "damage_instance_color",
            "fused_overlay",
            "road_status_color",
            "building_instance_mask",
        },
    )
    evidence_by_id = {item["evidence_id"]: item for item in evidence}
    assert evidence_by_id["B0001"]["bbox"]["x_min"] == 10
    assert evidence_by_id["B0001"]["confidence"] == 0.82
    assert "SCENE_BUILDING_SUMMARY" in evidence_by_id
    assert "R0001" in evidence_by_id
    assert "VIS_DAMAGE_MAP" in evidence_by_id
    assert "VIS_BUILDING_INSTANCE_MASK" in evidence_by_id

    claims = add_claim_types(
        [
            {
                "claim_id": "C001",
                "claim": "A building shows severe structural damage.",
                "language": "en",
                "related_evidence_ids": [],
            },
            {
                "claim_id": "C002",
                "claim": "The main road appears blocked.",
                "language": "en",
                "related_evidence_ids": [],
            },
        ]
    )
    linked = link_claims_to_evidence(claims, evidence)
    assert linked[0]["claim_type"] == "building_damage_level"
    assert "B0001" in linked[0]["related_evidence_ids"]
    assert "VIS_DAMAGE_MAP" in linked[0]["related_evidence_ids"]
    assert linked[1]["claim_type"] == "road_impact"
    assert "R0001" in linked[1]["related_evidence_ids"]

    payload = build_agent3_verify_payload(
        job_id="job-001",
        sample_id="sample-001",
        evidence_list=evidence,
        claim_list=linked,
        evidence_schema_version="agent1-ledger-2.1-to-evidence-list-v1",
    )
    assert payload["claim_list"][0]["related_evidence_ids"]


def test_explicit_unknown_evidence_id_is_rejected():
    evidence = build_evidence_list(sample_ledger())
    claims = add_claim_types(
        [
            {
                "claim_id": "C001",
                "claim": "The main road appears blocked.",
                "language": "en",
                "related_evidence_ids": ["NOT_REAL"],
            }
        ]
    )
    with pytest.raises(ValueError, match="unknown evidence IDs"):
        link_claims_to_evidence(claims, evidence)
