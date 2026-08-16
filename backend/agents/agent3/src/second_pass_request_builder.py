"""Build an Agent3-V5.2 second-pass request after the first check.

The HTTP/service layer may attach a private ``second_pass_context`` to a
runtime request. The context is never sent to the model. When the first
check triggers the deterministic second-check policy, this module uses
that context to create localized crops when a reliable evidence bbox is
available, otherwise it falls back to the relevant full-scene artifacts.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .second_check_crop_builder import build_crop_bundle, build_mask_crop_bundle


class SecondPassUnavailable(RuntimeError):
    """Raised when no safe second-pass visual request can be built."""


def _parse_input(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if isinstance(value, str):
        try:
            obj = json.loads(value)
        except Exception as exc:
            raise SecondPassUnavailable(
                "Agent3 request input is not a JSON object"
            ) from exc
        if isinstance(obj, dict):
            return obj
    raise SecondPassUnavailable("Agent3 request input must be an object")


def _first_bbox(first_check: dict[str, Any], context: dict[str, Any]):
    bbox_by_id = context.get("bbox_by_evidence_id", {})
    if not isinstance(bbox_by_id, dict):
        return None, None

    for evidence_id in first_check.get("evidence_ids", []):
        if str(evidence_id) in bbox_by_id:
            return str(evidence_id), bbox_by_id[str(evidence_id)]
    return None, None


def _roi_mask(first_check: dict[str, Any], context: dict[str, Any]):
    """Select the semantic mask associated with road or surface evidence."""
    evidence_ids = [str(item) for item in first_check.get("evidence_ids", [])]
    assets = context.get("assets", {})
    if any(item.startswith("R") for item in evidence_ids):
        value = assets.get("road_status_map")
        return ("road", value) if value else (None, None)
    if any(item.startswith("S") for item in evidence_ids):
        value = assets.get("surface_change_mask")
        return ("surface", value) if value else (None, None)
    return None, None


def _full_image_order(policy: dict[str, Any]) -> list[str]:
    recommended = policy.get("recommended_inputs", [])
    mapping = {
        "pre_crop": "pre_image",
        "post_crop": "post_image",
        "target_mask_crop": "building_instance_mask",
        "damage_map_crop": "damage_map",
        "fused_overlay_crop": "fused_overlay",
        "road_status_map_crop": "road_status_map",
        "surface_change_mask_crop": "surface_change_mask",
    }

    result: list[str] = []
    for key in recommended:
        result.append(mapping.get(str(key), str(key)))
    return result


def _crop_image_map(bundle: dict[str, Any]) -> dict[str, str]:
    images = bundle.get("images", {})
    if not isinstance(images, dict):
        return {}

    result = {
        "pre_crop": images.get("pre_image"),
        "post_crop": images.get("post_image"),
        "target_mask_crop": images.get("building_instance_mask"),
        "damage_map_crop": images.get("damage_map"),
        "fused_overlay_crop": images.get("fused_overlay"),
        "road_status_map_crop": images.get("road_status_map"),
        "surface_change_mask_crop": images.get("surface_change_mask"),
    }
    return {k: v for k, v in result.items() if v}


def build_second_pass_from_context(
    request: dict[str, Any],
    first_check: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    context = request.get("second_pass_context")
    if not isinstance(context, dict):
        raise SecondPassUnavailable("second_pass_context is missing")

    assets = context.get("assets", {})
    if not isinstance(assets, dict):
        raise SecondPassUnavailable("second_pass_context.assets is invalid")

    inp = _parse_input(request.get("input", {}))
    evidence_id, bbox = _first_bbox(first_check, context)
    roi_mode, roi_mask = _roi_mask(first_check, context)

    image_map: dict[str, str] = {}
    localization: dict[str, Any]

    if bbox is not None and context.get("work_dir"):
        try:
            bundle = build_crop_bundle(
                evidence_id=evidence_id or "UNKNOWN",
                bbox=bbox,
                assets=assets,
                output_dir=Path(context["work_dir"]) / str(first_check.get("claim_id", "claim")),
                padding_ratio=float(context.get("padding_ratio", 0.15)),
            )
            image_map = _crop_image_map(bundle)
            localization = {
                "mode": "localized_bbox_crop",
                "evidence_id": evidence_id,
                "crop_bbox": bundle.get("crop_bbox"),
            }
        except (OSError, ValueError, TypeError):
            image_map = {}
            localization = {"mode": "full_image_fallback"}
    elif roi_mode is not None and roi_mask and context.get("work_dir"):
        try:
            bundle = build_mask_crop_bundle(
                evidence_id=evidence_id or f"{roi_mode.upper()}_ROI",
                mask_path=roi_mask,
                mode=roi_mode,
                assets=assets,
                output_dir=Path(context["work_dir"]) / str(first_check.get("claim_id", "claim")),
            )
            image_map = _crop_image_map(bundle)
            localization = {
                "mode": f"{roi_mode}_semantic_mask_crop",
                "evidence_id": evidence_id or f"{roi_mode.upper()}_ROI",
                "crop_bbox": bundle.get("crop_bbox"),
            }
        except (OSError, ValueError, TypeError):
            image_map = {}
            localization = {"mode": "full_image_fallback"}
    else:
        localization = {"mode": "full_image_fallback"}

    if image_map:
        desired_order = [
            str(x) for x in policy.get("recommended_inputs", [])
            if str(x) in image_map
        ]
    else:
        desired_order = []
        for key in _full_image_order(policy):
            if key in assets and assets[key]:
                image_map[key] = str(assets[key])
                desired_order.append(key)

    if len(desired_order) < 2:
        raise SecondPassUnavailable(
            "Fewer than two usable images are available for second pass"
        )

    images = [image_map[key] for key in desired_order]

    second_input = copy.deepcopy(inp)
    second_input["verification_stage"] = "second_pass"
    second_input["first_check"] = copy.deepcopy(first_check)
    second_input["image_order"] = desired_order
    second_input["localization"] = localization

    prefix = "\n".join("<image>" for _ in images)
    instruction = (
        prefix
        + "\nRe-check the SAME atomic claim using only these claim-relevant "
          "visual inputs and the structured evidence already supplied. "
          "Do not introduce new facts. Return the same strict JSON schema."
    )

    return {
        "system": request.get("system"),
        "instruction": instruction,
        "input": second_input,
        "images": images,
    }
