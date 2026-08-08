"""Stable Agent1 entrypoint used by the shared orchestrator."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path, PureWindowsPath
from typing import Any


MODEL_ENVIRONMENTS = {
    "building": "AGENT1_BUILDING_MODEL_PATH",
    "damage": "AGENT1_DAMAGE_MODEL_PATH",
    "road_binary": "AGENT1_ROAD_BINARY_MODEL_PATH",
    "road_status": "AGENT1_ROAD_STATUS_MODEL_PATH",
}

ARTIFACT_TYPES = {
    "building/damage_instance_color.png": "damage_instance_color",
    "road/road_status_color.png": "road_status_color",
    "road/road_affected_probability.png": "road_affected_probability",
    "fusion/fused_color.png": "fused_color",
    "fusion/fused_overlay.png": "fused_overlay",
    "fusion/visual_compare.png": "visual_compare",
    "for_agent3/evidence_ledger_core.json": "evidence_ledger",
    "for_agent4/agent1_report_summary.json": "report_summary",
    "for_agent4/review_flags.json": "review_flags",
    "run_manifest.json": "run_manifest",
}
SAMPLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _required_path(payload: dict[str, Any], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise ValueError(f"Agent1 payload 缺少必填路径字段：{key}")
    path = Path(value)
    if not path.is_file():
        raise FileNotFoundError(f"Agent1 输入文件不存在：{key}={path}")
    return path


def _model_paths(config: dict[str, Any]) -> dict[str, Path]:
    configured = config.get("model_paths") or {}
    if not isinstance(configured, dict):
        raise TypeError("Agent1 config.model_paths 必须是字典")
    paths: dict[str, Path] = {}
    for key, environment in MODEL_ENVIRONMENTS.items():
        value = configured.get(key) or os.environ.get(environment)
        if value:
            paths[key] = Path(value)
    return paths


def _looks_absolute(value: str) -> bool:
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _sanitize_value(value: Any, work_dir: Path) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_value(item, work_dir) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item, work_dir) for item in value]
    if not isinstance(value, str) or not _looks_absolute(value):
        return value

    candidate = Path(value)
    try:
        return candidate.resolve().relative_to(work_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return PureWindowsPath(value).name or candidate.name


def _sanitize_generated_json(sample_root: Path, work_dir: Path) -> None:
    for path in sample_root.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        sanitized = _sanitize_value(payload, work_dir)
        path.write_text(
            json.dumps(sanitized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _artifact_list(sample_root: Path, work_dir: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative, artifact_type in ARTIFACT_TYPES.items():
        path = sample_root / relative
        if path.is_file():
            artifacts.append(
                {
                    "artifact_type": artifact_type,
                    "path": path.relative_to(work_dir).as_posix(),
                }
            )
    return artifacts


def _read_json_artifact(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def run(
    payload: dict[str, Any],
    work_dir: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the real four-model Agent1 pipeline.

    Explicit ``config`` values take precedence over environment variables.
    Model weights remain external to the repository, and returned paths are
    always relative to ``work_dir``.
    """

    from backend.agents.agent1.src.pipeline import Agent1Pipeline

    config = dict(config or {})
    sample_id = str(payload.get("sample_id") or "").strip()
    if not sample_id:
        raise ValueError("Agent1 payload 缺少必填字段：sample_id")
    if not SAMPLE_ID_PATTERN.fullmatch(sample_id):
        raise ValueError("Agent1 sample_id 只能包含字母、数字、点、下划线和连字符")

    pre_image = _required_path(payload, "pre_image")
    post_image = _required_path(payload, "post_image")
    task_root = Path(work_dir).resolve()
    task_root.mkdir(parents=True, exist_ok=True)
    output_root = task_root / "agent1"

    checkpoint_dir_value = config.get("checkpoint_dir") or os.environ.get(
        "AGENT1_CHECKPOINT_DIR"
    )
    pipeline = Agent1Pipeline(
        image_size=int(config.get("image_size", 512)),
        device=config.get("device") or os.environ.get("AGENT1_DEVICE"),
        model_paths=_model_paths(config),
        checkpoint_dir=Path(checkpoint_dir_value) if checkpoint_dir_value else None,
    )
    raw_result = pipeline.run_one(
        pre_image_path=pre_image,
        post_image_path=post_image,
        sample_id=sample_id,
        output_root=output_root,
        overwrite=bool(config.get("overwrite", True)),
    )

    sample_root = output_root / sample_id
    _sanitize_generated_json(sample_root, task_root)
    review_flags = _read_json_artifact(
        sample_root / "for_agent4" / "review_flags.json"
    )
    result = {
        "source_schema_version": "2.1",
        "source_schema_versions": {
            "evidence_ledger": "2.1",
            "report_summary": "1.1",
            "review_flags": "1.2",
        },
        "agent_code": "agent1",
        "capability": "visual_evidence",
        "sample_id": sample_id,
        "status": "succeeded",
        "summary": {
            "total_buildings": raw_result["total_buildings"],
            "damaged_buildings": raw_result["damaged_buildings"],
            "building_damage_ratio": raw_result["building_damage_ratio"],
            "affected_road_ratio": raw_result["affected_road_ratio"],
            "scene_risk_level": raw_result["scene_risk_level"],
            "review_required": raw_result["review_required"],
        },
        "review_flags": review_flags,
        "artifacts": _artifact_list(sample_root, task_root),
    }
    json.dumps(result, ensure_ascii=False)
    return result
