# -*- coding: utf-8 -*-
"""
32_run_agent1_random20_ebd.py

功能：
1. 扫描 EBD 数据集中完整的灾前/灾后图像对；
2. 使用固定随机种子随机抽取 20 条样本；
3. 只初始化一次 Agent1Pipeline，四个模型只加载一次；
4. 逐条运行第31步封装好的 Agent1；
5. 每条样本独立生成一个文件夹；
6. 每条样本文件夹包含给 Agent3 和 Agent4 的输出；
7. 生成抽样清单、运行汇总 JSON、运行汇总 CSV；
8. 某条样本失败时记录 error.txt，但不中断其余样本。

默认输出到 ``AGENT1_WORKSPACE`` 下的 Agent1 运行目录。
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import random
import traceback
from pathlib import Path
from typing import Dict, List

from backend.agents.agent1.training.config import workspace_root


PROJECT_ROOT = workspace_root()

EBD_IMAGES_ROOT = (
    PROJECT_ROOT
    / "data"
    / "EBD"
    / "EBDprocessed"
    / "images"
)

AGENT1_PIPELINE_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "pipeline.py"
)

OUTPUTS_ROOT = (
    PROJECT_ROOT
    / "agent1_visual_evidence"
    / "outputs"
)

DEFAULT_COUNT = 20
DEFAULT_SEED = 20260707

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
}


def import_agent1_pipeline():
    if not AGENT1_PIPELINE_SCRIPT.exists():
        raise FileNotFoundError(
            "找不到第31步智能体封装脚本：\n"
            f"{AGENT1_PIPELINE_SCRIPT}"
        )

    spec = importlib.util.spec_from_file_location(
        "agent1_pipeline_module",
        str(AGENT1_PIPELINE_SCRIPT),
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            "无法创建第31步脚本的导入配置：\n"
            f"{AGENT1_PIPELINE_SCRIPT}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "Agent1Pipeline"):
        raise AttributeError(
            "31_agent1_pipeline.py 中没有找到 "
            "Agent1Pipeline 类。"
        )

    return module


def collect_ebd_pairs() -> List[Dict[str, str]]:
    """
    递归扫描 EBD 图像目录，只保留完整的灾前、灾后图像对。
    """
    if not EBD_IMAGES_ROOT.exists():
        raise FileNotFoundError(
            "找不到 EBD 图像目录：\n"
            f"{EBD_IMAGES_ROOT}"
        )

    pre_map: Dict[str, Path] = {}
    post_map: Dict[str, Path] = {}

    for path in EBD_IMAGES_ROOT.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        stem = path.stem

        if stem.endswith("_pre_disaster"):
            sample_id = stem[:-len("_pre_disaster")]
            pre_map[sample_id] = path

        elif stem.endswith("_post_disaster"):
            sample_id = stem[:-len("_post_disaster")]
            post_map[sample_id] = path

    sample_ids = sorted(
        set(pre_map.keys())
        & set(post_map.keys())
    )

    return [
        {
            "sample_id": sample_id,
            "pre_image": str(pre_map[sample_id]),
            "post_image": str(post_map[sample_id]),
        }
        for sample_id in sample_ids
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "从 EBD 随机抽取样本并批量运行 Agent1。"
        )
    )

    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help="随机抽取数量，默认20。",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="随机种子，默认20260707。",
    )

    parser.add_argument(
        "--device",
        default=None,
        help=(
            "运行设备，例如 cuda 或 cpu；"
            "不填写时自动判断。"
        ),
    )

    parser.add_argument(
        "--run_name",
        default=None,
        help=(
            "输出文件夹名称；"
            "不填写时自动生成。"
        ),
    )

    parser.add_argument(
        "--exclude_sample_id",
        action="append",
        default=[],
        help=(
            "排除指定样本，可重复填写。"
        ),
    )

    return parser.parse_args()


def save_selected_samples(
    selected_pairs: List[Dict[str, str]],
    count: int,
    seed: int,
    output_path: Path,
):
    payload = {
        "schema_version": "1.0",
        "sampling_source": str(EBD_IMAGES_ROOT),
        "sampling_method": "python_random_sample",
        "random_seed": seed,
        "sample_count": count,
        "samples": selected_pairs,
    }

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )


def save_run_summary(
    run_name: str,
    run_root: Path,
    count_requested: int,
    random_seed: int,
    selected_samples_path: Path,
    results: List[Dict],
):
    success_count = sum(
        item.get("status") == "success"
        for item in results
    )

    failed_count = len(results) - success_count

    summary = {
        "schema_version": "1.0",
        "run_name": run_name,
        "run_root": str(run_root),
        "count_requested": count_requested,
        "random_seed": random_seed,
        "success_count": success_count,
        "failed_count": failed_count,
        "selected_samples_file": str(
            selected_samples_path
        ),
        "results": results,
    }

    summary_json_path = (
        run_root
        / "agent1_run_summary.json"
    )

    with open(
        summary_json_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            summary,
            file,
            ensure_ascii=False,
            indent=2,
        )

    summary_csv_path = (
        run_root
        / "agent1_run_summary.csv"
    )

    fieldnames = [
        "sample_id",
        "status",
        "pre_image_source",
        "post_image_source",
        "sample_root",
        "total_buildings",
        "damaged_buildings",
        "building_damage_ratio",
        "affected_road_ratio",
        "scene_risk_level",
        "review_required",
        "run_manifest",
        "agent3_ledger",
        "agent4_summary",
        "agent4_review_flags",
        "error",
        "error_path",
    ]

    with open(
        summary_csv_path,
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

        for record in results:
            writer.writerow(record)

    return (
        summary_json_path,
        summary_csv_path,
        success_count,
        failed_count,
    )


def main():
    args = parse_args()

    print("=" * 100)
    print("第32步：EBD随机20条样本运行Agent1")
    print("=" * 100)
    print(f"EBD图像目录：{EBD_IMAGES_ROOT}")
    print(f"随机数量：{args.count}")
    print(f"随机种子：{args.seed}")

    all_pairs = collect_ebd_pairs()

    excluded_ids = set(
        args.exclude_sample_id
    )

    if excluded_ids:
        all_pairs = [
            item
            for item in all_pairs
            if item["sample_id"]
            not in excluded_ids
        ]

    print(
        "排除后可用完整图像对数量："
        f"{len(all_pairs)}"
    )

    if args.count <= 0:
        raise ValueError(
            "--count 必须大于0。"
        )

    if len(all_pairs) < args.count:
        raise ValueError(
            f"当前仅找到 {len(all_pairs)} 条完整图像对，"
            f"无法抽取 {args.count} 条。"
        )

    random_generator = random.Random(
        args.seed
    )

    selected_pairs = random_generator.sample(
        all_pairs,
        args.count,
    )

    selected_pairs = sorted(
        selected_pairs,
        key=lambda item: item["sample_id"],
    )

    run_name = (
        args.run_name
        if args.run_name
        else (
            f"agent1_random{args.count}"
            f"_seed{args.seed}"
        )
    )

    run_root = (
        OUTPUTS_ROOT
        / run_name
    )

    run_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    selected_samples_path = (
        run_root
        / "selected_samples.json"
    )

    save_selected_samples(
        selected_pairs=selected_pairs,
        count=args.count,
        seed=args.seed,
        output_path=selected_samples_path,
    )

    print(f"运行输出目录：{run_root}")
    print(
        "随机样本清单："
        f"{selected_samples_path}"
    )

    agent1_module = import_agent1_pipeline()

    pipeline = agent1_module.Agent1Pipeline(
        project_root=PROJECT_ROOT,
        image_size=agent1_module.IMAGE_SIZE,
        device=args.device,
    )

    results = []

    for index, item in enumerate(
        selected_pairs,
        start=1,
    ):
        sample_id = item["sample_id"]
        pre_path = Path(
            item["pre_image"]
        )
        post_path = Path(
            item["post_image"]
        )

        print("=" * 100)
        print(
            f"[{index}/{len(selected_pairs)}] "
            f"运行：{sample_id}"
        )
        print(f"灾前图：{pre_path}")
        print(f"灾后图：{post_path}")

        try:
            result = pipeline.run_one(
                pre_image_path=pre_path,
                post_image_path=post_path,
                sample_id=sample_id,
                output_root=run_root,
                overwrite=True,
            )

            result[
                "pre_image_source"
            ] = str(pre_path)

            result[
                "post_image_source"
            ] = str(post_path)

            result["error"] = ""
            result["error_path"] = ""

            results.append(result)

            print(
                "运行成功："
                f"buildings="
                f"{result['total_buildings']}, "
                f"damaged="
                f"{result['damaged_buildings']}, "
                f"building_ratio="
                f"{result['building_damage_ratio']:.4f}, "
                f"road_ratio="
                f"{result['affected_road_ratio']:.4f}, "
                f"risk="
                f"{result['scene_risk_level']}, "
                f"review="
                f"{result['review_required']}"
            )

        except Exception as error:
            error_trace = (
                traceback.format_exc()
            )

            failed_sample_root = (
                run_root
                / sample_id
            )

            failed_sample_root.mkdir(
                parents=True,
                exist_ok=True,
            )

            error_path = (
                failed_sample_root
                / "error.txt"
            )

            with open(
                error_path,
                "w",
                encoding="utf-8",
            ) as file:
                file.write(
                    error_trace
                )

            failed_record = {
                "sample_id": sample_id,
                "status": "failed",
                "pre_image_source": str(
                    pre_path
                ),
                "post_image_source": str(
                    post_path
                ),
                "sample_root": str(
                    failed_sample_root
                ),
                "total_buildings": "",
                "damaged_buildings": "",
                "building_damage_ratio": "",
                "affected_road_ratio": "",
                "scene_risk_level": "",
                "review_required": "",
                "run_manifest": "",
                "agent3_ledger": "",
                "agent4_summary": "",
                "agent4_review_flags": "",
                "error": str(error),
                "error_path": str(
                    error_path
                ),
            }

            results.append(
                failed_record
            )

            print(
                f"[失败] {sample_id}"
            )

            print(
                f"错误：{error}"
            )

            print(
                "完整错误已保存："
                f"{error_path}"
            )

        save_run_summary(
            run_name=run_name,
            run_root=run_root,
            count_requested=args.count,
            random_seed=args.seed,
            selected_samples_path=(
                selected_samples_path
            ),
            results=results,
        )

    (
        summary_json_path,
        summary_csv_path,
        success_count,
        failed_count,
    ) = save_run_summary(
        run_name=run_name,
        run_root=run_root,
        count_requested=args.count,
        random_seed=args.seed,
        selected_samples_path=(
            selected_samples_path
        ),
        results=results,
    )

    print("=" * 100)
    print("第32步运行完成")
    print("=" * 100)
    print(f"成功数量：{success_count}")
    print(f"失败数量：{failed_count}")
    print(
        "随机样本清单："
        f"{selected_samples_path}"
    )
    print(
        "运行汇总JSON："
        f"{summary_json_path}"
    )
    print(
        "运行汇总CSV："
        f"{summary_csv_path}"
    )
    print(
        "所有样本输出根目录："
        f"{run_root}"
    )
    print("=" * 100)


if __name__ == "__main__":
    main()
