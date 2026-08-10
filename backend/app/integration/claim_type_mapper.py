"""Deterministic Agent2 claim classification for the Agent3 contract.

The mapper runs after Agent2 inference.  It never changes the original
description or claim text and therefore does not alter the trained model.
"""

from __future__ import annotations

import re
from typing import Any


CLAIM_TYPE_MAPPER_VERSION = "keyword-rules-v1"
FROZEN_CLAIM_TYPES = frozenset(
    {
        "agricultural_change",
        "building_damage_level",
        "building_damage_presence",
        "building_damage_quantity",
        "disaster_type_inference",
        "generic_visual_change",
        "other",
        "road_displacement",
        "road_impact",
        "terrain_change",
        "vegetation_change",
        "water_change",
    }
)


def _contains(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def infer_claim_type(claim_text: str) -> str:
    """Classify one English atomic claim into the frozen Agent3 registry."""

    text = " ".join(str(claim_text or "").split())
    if not text:
        raise ValueError("claim text must not be empty")

    building = _contains(text, r"\b(building|buildings|structure|structures|house|houses)\b")
    road = _contains(
        text,
        r"\b(road|roads|roadway|roadways|street|streets|route|routes|highway|highways|bridge|bridges)\b",
    )

    if building and _contains(
        text,
        r"\b(how many|number|count|total|several|multiple|many|few|no|none|zero|percent|percentage|ratio|proportion)\b",
    ):
        return "building_damage_quantity"
    if building and _contains(
        text,
        r"\b(minor|major|severe|severity|destroyed|destruction|collapsed|collapse|level|degree)\b",
    ):
        return "building_damage_level"
    if building and _contains(
        text,
        r"\b(damage|damaged|destroyed|collapsed|affected|intact|unchanged)\b",
    ):
        return "building_damage_presence"

    if road and _contains(
        text,
        r"\b(displaced|displacement|shifted|shift|offset|misalign|misaligned|relocated)\b",
    ):
        return "road_displacement"
    if road and _contains(
        text,
        r"\b(damage|damaged|affected|blocked|obstructed|impassable|disrupted|inaccessible|intact|accessible|impact)\b",
    ):
        return "road_impact"

    if _contains(
        text,
        r"\b(crop|crops|cropland|farmland|farm|farms|agricultural|agriculture|field|fields)\b",
    ):
        return "agricultural_change"
    if _contains(
        text,
        r"\b(water|floodwater|river|lake|coast|coastal|shoreline|flooded|flooding|inundated|inundation)\b",
    ):
        return "water_change"
    if _contains(
        text,
        r"\b(vegetation|forest|forested|tree|trees|canopy|greenery|grassland)\b",
    ):
        return "vegetation_change"
    if _contains(
        text,
        r"\b(terrain|landslide|landslides|slope|ground|soil|erosion|debris|landform)\b",
    ):
        return "terrain_change"
    if _contains(
        text,
        r"\b(earthquake|wildfire|hurricane|cyclone|typhoon|tornado|tsunami|disaster type|type of disaster)\b",
    ):
        return "disaster_type_inference"
    if _contains(
        text,
        r"\b(change|changed|difference|different|appears|visible|observed|affected|damage)\b",
    ):
        return "generic_visual_change"
    return "other"


def add_claim_types(claim_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copied claim list with valid frozen ``claim_type`` values."""

    if not isinstance(claim_list, list) or not claim_list:
        raise ValueError("claim_list must be a non-empty list")

    result: list[dict[str, Any]] = []
    for item in claim_list:
        if not isinstance(item, dict):
            raise TypeError("claim_list items must be objects")
        claim = dict(item)
        claim_text = claim.get("claim")
        if not isinstance(claim_text, str) or not claim_text.strip():
            raise ValueError("each claim must contain non-empty claim text")

        existing = str(claim.get("claim_type") or "").strip()
        if existing:
            if existing not in FROZEN_CLAIM_TYPES:
                raise ValueError(f"unsupported claim_type: {existing}")
            claim_type = existing
            source = str(claim.get("claim_type_source") or "upstream")
        else:
            claim_type = infer_claim_type(claim_text)
            source = CLAIM_TYPE_MAPPER_VERSION

        claim["claim_type"] = claim_type
        claim["claim_type_source"] = source
        result.append(claim)
    return result
