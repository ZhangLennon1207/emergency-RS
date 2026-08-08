"""Stable Agent2 entrypoint used by the shared orchestrator."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


SAMPLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _required_path(payload: dict[str, Any], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise ValueError(f"Agent2 payload 缺少必填路径字段：{key}")
    path = Path(value)
    if not path.is_file():
        raise FileNotFoundError(f"Agent2 输入文件不存在：{key}={path}")
    return path


def _load_pipeline_class():
    from backend.agents.agent2.src.pipeline import Agent2Pipeline

    return Agent2Pipeline


def _build_claim_list(description: str) -> list[dict[str, Any]]:
    from backend.agents.agent2.src.claim_builder import build_claim_list

    return build_claim_list(description)


def run(
    payload: dict[str, Any],
    work_dir: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Qwen2.5-VL + local LoRA and return an unverified description."""

    config = dict(config or {})
    sample_id = str(payload.get("sample_id") or "").strip()
    if not SAMPLE_ID_PATTERN.fullmatch(sample_id):
        raise ValueError("Agent2 sample_id 只能包含字母、数字、点、下划线和连字符")
    pre_image = _required_path(payload, "pre_image")
    post_image = _required_path(payload, "post_image")

    base_model_path = config.get("base_model_path") or os.environ.get(
        "AGENT2_BASE_MODEL_PATH"
    )
    lora_path = config.get("lora_path") or os.environ.get("AGENT2_LORA_PATH")
    if not base_model_path:
        raise ValueError("缺少 Agent2 基础模型路径配置")
    if not lora_path:
        raise ValueError("缺少 Agent2 LoRA 路径配置")

    task_root = Path(work_dir).resolve()
    output_root = task_root / "agent2"
    offload_dir = output_root / "model_offload"
    pipeline_class = _load_pipeline_class()
    pipeline = pipeline_class(
        gpu_memory=str(config.get("gpu_memory", "6GiB")),
        cpu_memory=str(config.get("cpu_memory", "24GiB")),
        base_model_path=base_model_path,
        lora_path=lora_path,
        prompt_path=config.get("prompt_path")
        or Path(__file__).resolve().parent / "src" / "prompts" / "paired.txt",
        offload_dir=offload_dir,
    )
    raw_result = pipeline.run_one(
        pre_image_path=pre_image,
        post_image_path=post_image,
        sample_id=sample_id,
        output_root=output_root,
        max_new_tokens=int(config.get("max_new_tokens", 320)),
        overwrite=bool(config.get("overwrite", True)),
    )

    sample_root = output_root / sample_id
    artifacts = []
    for file_name, artifact_type in (
        ("agent2_output.json", "change_description"),
        ("raw_response.txt", "raw_model_response"),
        ("prompt_snapshot.txt", "prompt_snapshot"),
        ("run_manifest.json", "run_manifest"),
    ):
        path = sample_root / file_name
        if path.is_file():
            artifacts.append(
                {
                    "artifact_type": artifact_type,
                    "path": path.relative_to(task_root).as_posix(),
                }
            )

    description = raw_result["description"]
    claim_list = raw_result.get("claim_list")
    if not isinstance(claim_list, list) or not claim_list:
        claim_list = _build_claim_list(description)

    result = {
        "source_schema_version": "1.1",
        "agent_code": "agent2",
        "capability": "change_description",
        "sample_id": sample_id,
        "status": "succeeded",
        "language": "en",
        "description": description,
        "claim_builder_version": "sentence-span-v1",
        "claim_list": claim_list,
        "verification_status": "unverified",
        "notice": "模型生成的变化描述，尚未经过证据校验。",
        "artifacts": artifacts,
    }
    json.dumps(result, ensure_ascii=False)
    return result
