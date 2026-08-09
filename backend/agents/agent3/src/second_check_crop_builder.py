"""
Deterministic visual crop builder for Agent3-V5.2 second checks.

The builder never changes a verification decision. It crops aligned
visual artifacts using an Agent1 evidence bbox already present in the
structured evidence ledger.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image


SUPPORTED_ASSETS = (
    "pre_image",
    "post_image",
    "damage_map",
    "fused_overlay",
    "road_status_map",
    "building_instance_mask",
)


def normalize_bbox(bbox: Any) -> tuple[int, int, int, int]:
    if isinstance(bbox, dict):
        keys = ("x_min", "y_min", "x_max", "y_max")
        if all(k in bbox for k in keys):
            values = tuple(int(bbox[k]) for k in keys)
        else:
            raise ValueError(f"Unsupported bbox mapping: {bbox!r}")
    elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        values = tuple(int(x) for x in bbox)
    else:
        raise ValueError(f"Unsupported bbox: {bbox!r}")

    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid bbox coordinates: {values!r}")
    return values


def padded_bbox(
    bbox: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    padding_ratio: float = 0.15,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)
    px = round(bw * padding_ratio)
    py = round(bh * padding_ratio)

    result = (
        max(0, x1 - px),
        max(0, y1 - py),
        min(width, x2 + px),
        min(height, y2 + py),
    )

    if result[2] <= result[0] or result[3] <= result[1]:
        raise ValueError(f"BBox falls outside image bounds: {bbox!r}")
    return result


def build_crop_bundle(
    *,
    evidence_id: str,
    bbox: Any,
    assets: dict[str, str],
    output_dir: str | Path,
    padding_ratio: float = 0.15,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    available: dict[str, Path] = {}
    sizes: dict[str, tuple[int, int]] = {}

    for key in SUPPORTED_ASSETS:
        value = assets.get(key)
        if not value:
            continue

        path = Path(value)
        if not path.is_file():
            continue

        with Image.open(path) as img:
            sizes[key] = img.size
        available[key] = path

    if not available:
        raise ValueError("No usable image assets supplied")

    unique_sizes = set(sizes.values())
    if len(unique_sizes) != 1:
        raise ValueError(
            "Second-check artifacts must be pixel-aligned and have the "
            f"same dimensions; got {sizes!r}"
        )

    width, height = next(iter(unique_sizes))
    original_bbox = normalize_bbox(bbox)
    crop_box = padded_bbox(
        original_bbox,
        width=width,
        height=height,
        padding_ratio=padding_ratio,
    )

    outputs: dict[str, str] = {}

    for key, path in available.items():
        with Image.open(path) as img:
            crop = img.convert("RGB").crop(crop_box)
            target = output_dir / f"{key}_crop.png"
            crop.save(target, format="PNG")
            # Runtime-internal path only. HTTP responses must not expose it.
            outputs[key] = str(target)

    return {
        "evidence_id": str(evidence_id),
        "mode": "localized_bbox_crop",
        "source_image_size": [width, height],
        "original_bbox": list(original_bbox),
        "crop_bbox": list(crop_box),
        "padding_ratio": float(padding_ratio),
        "images": outputs,
    }
