# -*- coding: utf-8 -*-
"""
34_run_agent2_same20.py

读取 Agent1 已固定生成的同一批20条样本，
只加载一次 Agent2 模型，依次生成英文描述。
默认支持断点续跑：已经成功完成的样本会被跳过。
"""

from __future__ import annotations

import argparse
import csv
import gc
import importlib
import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import torch


AGENT2_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = Path(
    os.environ.get("AGENT2_EVAL_INPUT_ROOT", "external/agent1_same20")
)
DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get(
        "AGENT2_EVAL_OUTPUT_ROOT",
        str(AGENT2_ROOT / "outputs" / "agent2_same20"),
    )
)

EXPECTED_SAMPLE_COUNT = 20


def import_agent2_pipeline():
    """Import lazily so data-only checks do not require model dependencies."""

    return importlib.import_module("backend.agents.agent2.src.pipeline")


def load_sample_ids(input_root: Path) -> List[str]:
    if not input_root.exists():
        raise FileNotFoundError(
            "找不到 Agent1 固定20条样本目录：\n"
            f"{input_root}"
        )

    sample_ids: List[str] = []
    selected_samples = input_root / "selected_samples.json"

    if selected_samples.exists():
        with open(
            selected_samples,
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)

        for item in payload.get("samples", []):
            sample_id = item.get("sample_id")

            if sample_id:
                sample_ids.append(
                    str(sample_id)
                )

    else:
        for path in input_root.iterdir():
            if not path.is_dir():
                continue

            input_dir = path / "input"

            if (
                (input_dir / "pre_image.png").exists()
                and (input_dir / "post_image.png").exists()
            ):
                sample_ids.append(path.name)

    sample_ids = sorted(set(sample_ids))

    if not sample_ids:
        raise RuntimeError(
            "没有找到可用样本。"
        )

    if len(sample_ids) != EXPECTED_SAMPLE_COUNT:
        print(
            "[警告] 找到的样本数量不是20："
            f"{len(sample_ids)}"
        )

    return sample_ids


def build_sample_record(
    sample_id: str,
    input_root: Path,
) -> Dict[str, str]:
    sample_root = (
        input_root
        / sample_id
    )

    pre_image = (
        sample_root
        / "input"
        / "pre_image.png"
    )

    post_image = (
        sample_root
        / "input"
        / "post_image.png"
    )

    if not pre_image.exists():
        raise FileNotFoundError(
            f"{sample_id} 缺少灾前图：{pre_image}"
        )

    if not post_image.exists():
        raise FileNotFoundError(
            f"{sample_id} 缺少灾后图：{post_image}"
        )

    return {
        "sample_id": sample_id,
        "pre_image": str(pre_image),
        "post_image": str(post_image),
    }


def load_existing_success(
    output_root: Path,
    sample_id: str,
) -> Dict[str, Any] | None:
    sample_root = output_root / sample_id
    output_json = (
        sample_root
        / "agent2_output.json"
    )
    manifest_json = (
        sample_root
        / "run_manifest.json"
    )

    if not (
        output_json.exists()
        and manifest_json.exists()
    ):
        return None

    try:
        with open(
            manifest_json,
            "r",
            encoding="utf-8",
        ) as file:
            manifest = json.load(file)

        if manifest.get("status") != "success":
            return None

        with open(
            output_json,
            "r",
            encoding="utf-8",
        ) as file:
            output_payload = json.load(file)

        description = output_payload.get(
            "description",
            "",
        )

        if not description:
            return None

        return {
            "sample_id": sample_id,
            "status": "success",
            "execution_mode": "skipped_existing",
            "description": description,
            "sample_root": str(sample_root),
            "agent2_output": str(output_json),
            "run_manifest": str(manifest_json),
            "error": "",
            "error_path": "",
        }

    except Exception:
        return None


def save_summary(
    output_root: Path,
    results: List[Dict[str, Any]],
    sample_count: int,
):
    success_count = sum(
        item.get("status") == "success"
        for item in results
    )
    failed_count = sum(
        item.get("status") == "failed"
        for item in results
    )

    summary = {
        "schema_version": "1.0",
        "run_name": output_root.name,
        "agent1_source": "configured_external_evaluation_batch",
        "agent2_output": output_root.name,
        "sample_count_expected": sample_count,
        "processed_record_count": len(results),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
    }

    summary_json = (
        output_root
        / "agent2_run_summary.json"
    )

    with open(
        summary_json,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            summary,
            file,
            ensure_ascii=False,
            indent=2,
        )

    summary_csv = (
        output_root
        / "agent2_run_summary.csv"
    )

    fieldnames = [
        "sample_id",
        "status",
        "execution_mode",
        "pre_image",
        "post_image",
        "description",
        "sample_root",
        "agent2_output",
        "run_manifest",
        "error",
        "error_path",
    ]

    with open(
        summary_csv,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()

        for item in results:
            writer.writerow(item)

    return (
        summary_json,
        summary_csv,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "对 Agent1 固定同一批20条样本运行 Agent2。"
        )
    )

    parser.add_argument(
        "--input_root",
        default=str(DEFAULT_INPUT_ROOT),
        help="Directory containing Agent1 sample folders and selected_samples.json.",
    )

    parser.add_argument(
        "--output_root",
        default=str(
            DEFAULT_OUTPUT_ROOT
        ),
    )

    parser.add_argument(
        "--base_model_path",
        default=os.environ.get("AGENT2_BASE_MODEL_PATH"),
    )

    parser.add_argument(
        "--lora_path",
        default=os.environ.get("AGENT2_LORA_PATH"),
    )

    parser.add_argument(
        "--prompt_path",
        default=str(AGENT2_ROOT / "src" / "prompts" / "paired.txt"),
    )

    parser.add_argument(
        "--offload_dir",
        default=None,
    )

    parser.add_argument(
        "--gpu_memory",
        default="6GiB",
    )

    parser.add_argument(
        "--cpu_memory",
        default="24GiB",
    )

    parser.add_argument(
        "--max_new_tokens",
        type=int,
        default=320,
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="强制重新生成已成功样本。",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    input_root = Path(args.input_root)
    output_root = Path(
        args.output_root
    )
    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 100)
    print("第34步：Agent2处理Agent1固定同一批20条样本")
    print("=" * 100)
    print(
        f"Agent1样本目录：{input_root}"
    )
    print(
        f"Agent2输出目录：{output_root}"
    )
    print(
        f"断点续跑：{not args.overwrite}"
    )

    sample_ids = load_sample_ids(input_root)

    sample_records = [
        build_sample_record(sample_id, input_root)
        for sample_id in sample_ids
    ]

    results: List[Dict[str, Any]] = []
    pending_records: List[Dict[str, str]] = []

    for record in sample_records:
        existing = load_existing_success(
            output_root,
            record["sample_id"],
        )

        if (
            existing is not None
            and not args.overwrite
        ):
            existing["pre_image"] = (
                record["pre_image"]
            )
            existing["post_image"] = (
                record["post_image"]
            )
            results.append(existing)
            print(
                f"[跳过已完成] {record['sample_id']}"
            )
        else:
            pending_records.append(record)

    save_summary(
        output_root,
        results,
        len(sample_records),
    )

    if not pending_records:
        print(
            "全部样本此前已经成功完成。"
        )
        return

    print(
        f"本次实际推理数量：{len(pending_records)}"
    )

    agent2_module = import_agent2_pipeline()

    pipeline = agent2_module.Agent2Pipeline(
        gpu_memory=args.gpu_memory,
        cpu_memory=args.cpu_memory,
        base_model_path=args.base_model_path,
        lora_path=args.lora_path,
        prompt_path=args.prompt_path,
        offload_dir=args.offload_dir or output_root / "model_offload",
    )

    for index, record in enumerate(
        pending_records,
        start=1,
    ):
        sample_id = record["sample_id"]
        pre_image = Path(
            record["pre_image"]
        )
        post_image = Path(
            record["post_image"]
        )

        print("=" * 100)
        print(
            f"[{index}/{len(pending_records)}] "
            f"生成描述：{sample_id}"
        )

        start_time = datetime.now().isoformat(
            timespec="seconds"
        )

        try:
            result = pipeline.run_one(
                pre_image_path=pre_image,
                post_image_path=post_image,
                sample_id=sample_id,
                output_root=output_root,
                overwrite=True,
                max_new_tokens=(
                    args.max_new_tokens
                ),
            )

            result.update({
                "execution_mode": "generated",
                "pre_image": str(pre_image),
                "post_image": str(post_image),
                "start_time": start_time,
                "end_time": (
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                ),
                "error": "",
                "error_path": "",
            })

            results.append(result)

            print(
                f"生成成功：{result['description']}"
            )

        except Exception as error:
            sample_root = (
                output_root
                / sample_id
            )
            sample_root.mkdir(
                parents=True,
                exist_ok=True,
            )

            error_path = (
                sample_root
                / "error.txt"
            )

            if not error_path.exists():
                error_path.write_text(
                    traceback.format_exc(),
                    encoding="utf-8",
                )

            results.append({
                "sample_id": sample_id,
                "status": "failed",
                "execution_mode": "generated",
                "pre_image": str(pre_image),
                "post_image": str(post_image),
                "description": "",
                "sample_root": str(sample_root),
                "agent2_output": "",
                "run_manifest": str(
                    sample_root
                    / "run_manifest.json"
                ),
                "start_time": start_time,
                "end_time": (
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                ),
                "error": str(error),
                "error_path": str(error_path),
            })

            print(
                f"[失败] {sample_id}: {error}"
            )

        finally:
            gc.collect()

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        save_summary(
            output_root,
            results,
            len(sample_records),
        )

    (
        summary_json,
        summary_csv,
    ) = save_summary(
        output_root,
        results,
        len(sample_records),
    )

    success_count = sum(
        item.get("status") == "success"
        for item in results
    )
    failed_count = sum(
        item.get("status") == "failed"
        for item in results
    )

    print("=" * 100)
    print("第34步运行完成")
    print("=" * 100)
    print(f"成功数量：{success_count}")
    print(f"失败数量：{failed_count}")
    print(f"汇总JSON：{summary_json}")
    print(f"汇总CSV：{summary_csv}")
    print(f"输出根目录：{output_root}")
    print("=" * 100)


if __name__ == "__main__":
    main()
