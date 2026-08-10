from __future__ import annotations

from pathlib import Path
from typing import Any

from .schemas import VerifyPayload


SYSTEM = (
    "You are Agent3, an evidence-verification agent for paired pre/post-disaster "
    "remote-sensing imagery. Verify exactly one atomic claim against the supplied "
    "structured and visual evidence. Do not infer facts outside the evidence. "
    "Use exactly one support_status from: supported, partially_supported, unsupported, "
    "contradicted, exaggerated. Return strict JSON only."
)

BUILDING_CLAIM_TYPES = {
    "building_damage_level",
    "building_damage_presence",
    "building_damage_quantity",
}

ROAD_CLAIM_TYPES = {"road_displacement", "road_impact"}


def _image_order(claim_type: str, assets: dict[str, Path]) -> list[str]:
    """Select only claim-relevant rasters while always retaining pre/post."""
    if claim_type in BUILDING_CLAIM_TYPES:
        candidates = (
            "pre_image", "post_image", "damage_map", "fused_overlay",
            "building_instance_mask",
        )
    elif claim_type in ROAD_CLAIM_TYPES:
        candidates = (
            "pre_image", "post_image", "road_status_map", "fused_overlay",
        )
    else:
        candidates = ("pre_image", "post_image", "fused_overlay")
    return [key for key in candidates if key in assets]


def build_requests(payload: VerifyPayload, assets: dict[str, Path], work_dir: Path) -> list[dict[str, Any]]:
    evidence = {x.evidence_id: x for x in payload.evidence_list}
    result = []
    for claim in payload.claim_list:
        image_order = _image_order(claim.claim_type, assets)
        images = [str(assets[k]) for k in image_order]
        instruction = "\n".join(["<image>"] * len(images)) + (
            "\nImages are supplied in image_order. Verify only the atomic claim. "
            "Use structured and visual evidence conservatively. Do not use filenames "
            "or external knowledge as evidence."
        )
        selected = [evidence[eid].model_dump() for eid in claim.related_evidence_ids if eid in evidence]
        bbox_by_id = {
            item["evidence_id"]: item["bbox"] for item in selected if item.get("bbox") is not None
        }
        result.append({
            "system": SYSTEM,
            "instruction": instruction,
            "input": {
                "scene_uid": payload.sample_id,
                "claim_id": claim.claim_id,
                "atomic_claim": claim.claim,
                "claim_type": claim.claim_type,
                "structured_evidence": selected,
                "image_order": image_order,
                "confidence_policy": "Confidence values are uncalibrated model outputs.",
            },
            "images": images,
            "second_pass_context": {
                "assets": {k: str(v) for k, v in assets.items()},
                "bbox_by_evidence_id": bbox_by_id,
                "work_dir": str(work_dir / "second_pass"),
                "padding_ratio": 0.15,
            },
        })
    return result
