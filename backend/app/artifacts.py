from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SAFE_KEY = re.compile(r"^[a-z0-9][a-z0-9_]{0,95}$")
INDEX_NAME = "artifact_index.json"


def _inside(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def build_artifact_index(
    job_root: Path,
    job_id: str,
    agent_results: dict[str, dict[str, Any]],
) -> dict[str, str]:
    index: dict[str, str] = {
        "input_pre": "inputs/pre.png",
        "input_post": "inputs/post.png",
    }
    for agent_code, result in agent_results.items():
        for artifact in result.get("artifacts", []):
            if not isinstance(artifact, dict):
                continue
            artifact_type = str(artifact.get("artifact_type") or "").lower()
            key = f"{agent_code}_{artifact_type}"
            relative = str(artifact.get("path") or "")
            if not SAFE_KEY.fullmatch(key) or not relative:
                continue
            candidate = _inside(job_root, relative)
            if candidate is None or not candidate.is_file():
                continue
            suffix = 2
            original = key
            while key in index:
                key = f"{original}_{suffix}"
                suffix += 1
            index[key] = candidate.relative_to(job_root.resolve()).as_posix()

    (job_root / INDEX_NAME).write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    urls: dict[str, str] = {}
    for key, relative in index.items():
        candidate = _inside(job_root, relative)
        if candidate is not None and candidate.is_file():
            urls[key] = f"/api/v1/jobs/{job_id}/artifacts/{key}"
    return urls


def resolve_artifact(job_root: Path, artifact_key: str) -> Path | None:
    if not SAFE_KEY.fullmatch(artifact_key):
        return None
    index_path = job_root / INDEX_NAME
    if not index_path.is_file():
        return None
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    relative = index.get(artifact_key) if isinstance(index, dict) else None
    if not isinstance(relative, str):
        return None
    candidate = _inside(job_root, relative)
    return candidate if candidate and candidate.is_file() else None
