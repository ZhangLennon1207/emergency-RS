from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
from pathlib import Path
from typing import Any


SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ALLOWED_CROPS = {
    "pre_image_crop.png", "post_image_crop.png", "damage_map_crop.png",
    "fused_overlay_crop.png", "road_status_map_crop.png",
    "building_instance_mask_crop.png",
}


def _safe(value: str, label: str) -> str:
    if not SAFE.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def persist_second_check_artifacts(
    work_dir: Path, artifact_root: Path, *, job_id: str, sample_id: str,
) -> list[dict[str, Any]]:
    source_root = work_dir / "second_pass"
    if not source_root.is_dir():
        return []
    job_id = _safe(job_id, "job_id"); sample_id = _safe(sample_id, "sample_id")
    records = []
    for claim_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        claim_id = _safe(claim_dir.name, "claim_id")
        destination = artifact_root / job_id / sample_id / "second_check" / claim_id
        for source in sorted(claim_dir.iterdir()):
            if not source.is_file() or source.name not in ALLOWED_CROPS:
                continue
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / source.name
            shutil.copy2(source, target)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            records.append({
                "artifact_type": "second_check_crop",
                "claim_id": claim_id,
                "file_name": source.name,
                "media_type": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                "size_bytes": target.stat().st_size,
                "sha256": digest,
                "download_url": (
                    f"/api/v1/artifacts/{job_id}/{sample_id}/second_check/"
                    f"{claim_id}/{source.name}"
                ),
            })
    return records


def resolve_artifact(
    artifact_root: Path, *, job_id: str, sample_id: str, claim_id: str, file_name: str,
) -> Path | None:
    try:
        parts = [_safe(value, label) for value, label in (
            (job_id, "job_id"), (sample_id, "sample_id"),
            (claim_id, "claim_id"), (file_name, "file_name"),
        )]
    except ValueError:
        return None
    if file_name not in ALLOWED_CROPS:
        return None
    root = artifact_root.resolve()
    candidate = (root / parts[0] / parts[1] / "second_check" / parts[2] / parts[3]).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None
