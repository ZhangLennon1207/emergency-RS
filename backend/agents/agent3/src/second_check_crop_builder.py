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
    "surface_change_mask",
)


ROI_MODES = {
    "building": {"padding_ratio": 0.15},
    "road": {"padding_ratio": 0.08},
    "surface": {"padding_ratio": 0.12},
}


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
    min_width: int = 64,
    min_height: int = 64,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)
    px = round(bw * padding_ratio)
    py = round(bh * padding_ratio)

    result = [
        max(0, x1 - px),
        max(0, y1 - py),
        min(width, x2 + px),
        min(height, y2 + py),
    ]
    target_w = min(width, max(min_width, result[2] - result[0]))
    target_h = min(height, max(min_height, result[3] - result[1]))
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    result[0] = max(0, min(width - target_w, round(cx - target_w / 2)))
    result[1] = max(0, min(height - target_h, round(cy - target_h / 2)))
    result[2] = result[0] + target_w
    result[3] = result[1] + target_h
    result = tuple(int(value) for value in result)

    if result[2] <= result[0] or result[3] <= result[1]:
        raise ValueError(f"BBox falls outside image bounds: {bbox!r}")
    return result


def mask_bbox(mask_path: str | Path, *, mode: str) -> tuple[int, int, int, int]:
    """Return a local semantic ROI without an instance bbox.

    For road status maps, select the largest connected affected-road segment
    instead of the union of every road in the scene. This preserves locality
    when a network crosses the complete image.
    """
    with Image.open(mask_path) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        pixels = rgb.load()
        selected_pixels: set[tuple[int, int]] = set()
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                if mode == "road":
                    selected = r >= 120 and r > g * 1.2 and r > b * 1.2
                else:
                    selected = max(r, g, b) >= 20
                if selected:
                    selected_pixels.add((x, y))
    if not selected_pixels:
        raise ValueError(f"No {mode} ROI pixels found in {mask_path}")
    if mode != "road":
        xs, ys = zip(*selected_pixels)
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    # Eight-neighbour connectivity keeps diagonal road strokes together.
    largest: set[tuple[int, int]] = set()
    remaining = set(selected_pixels)
    while remaining:
        component = {remaining.pop()}
        frontier = list(component)
        while frontier:
            x, y = frontier.pop()
            for nx in range(x - 1, x + 2):
                for ny in range(y - 1, y + 2):
                    point = (nx, ny)
                    if point in remaining:
                        remaining.remove(point)
                        component.add(point)
                        frontier.append(point)
        if len(component) > len(largest):
            largest = component
    xs, ys = zip(*largest)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


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


def build_mask_crop_bundle(
    *,
    evidence_id: str,
    mask_path: str | Path,
    mode: str,
    assets: dict[str, str],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Build an aligned second-check bundle from a semantic ROI mask."""
    if mode not in ROI_MODES:
        raise ValueError(f"Unsupported ROI mode: {mode}")
    original_bbox = mask_bbox(mask_path, mode=mode)
    return build_crop_bundle(
        evidence_id=evidence_id,
        bbox=original_bbox,
        assets=assets,
        output_dir=output_dir,
        padding_ratio=ROI_MODES[mode]["padding_ratio"],
    )
