# -*- coding: utf-8 -*-
"""
22_check_spacenet8_structure.py

作用：
检查 SpaceNet 8 Germany 和 Louisiana-East 训练集结构。

主要检查：
1. 每个训练集是否存在 annotations / PRE-event / POST-event
2. 各文件夹中文件数量
3. 随机读取几个 geojson，看里面有哪些字段
4. 输出一个结构检查报告 txt
"""

import json
from pathlib import Path

from backend.agents.agent1.training.config import workspace_root


PROJECT_ROOT = workspace_root()

SPACENET8_ROOT = PROJECT_ROOT / "data" / "SpaceNet8"

DATASETS = [
    "Germany_Training_Public",
    "Louisiana-East_Training_Public",
]

OUTPUT_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "outputs" / "spacenet8_check"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_PATH = OUTPUT_DIR / "spacenet8_structure_report.txt"


IMAGE_EXTS = [".tif", ".tiff", ".png", ".jpg", ".jpeg"]


def list_files(folder, exts=None):
    if not folder.exists():
        return []

    files = []

    for p in folder.rglob("*"):
        if not p.is_file():
            continue

        if exts is None:
            files.append(p)
        else:
            if p.suffix.lower() in exts:
                files.append(p)

    return sorted(files)


def read_geojson_preview(path, max_features=3):
    result = {
        "path": str(path),
        "ok": False,
        "top_keys": [],
        "feature_count": 0,
        "feature_property_keys": [],
        "sample_properties": [],
    }

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        result["ok"] = True
        result["top_keys"] = list(data.keys())

        features = data.get("features", [])
        result["feature_count"] = len(features)

        property_keys = set()
        sample_properties = []

        for feat in features[:max_features]:
            props = feat.get("properties", {})
            property_keys.update(props.keys())
            sample_properties.append(props)

        result["feature_property_keys"] = sorted(list(property_keys))
        result["sample_properties"] = sample_properties

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    lines = []

    lines.append("=" * 80)
    lines.append("SpaceNet 8 数据结构检查报告")
    lines.append("=" * 80)
    lines.append(f"SPACENET8_ROOT = {SPACENET8_ROOT}")
    lines.append("")

    if not SPACENET8_ROOT.exists():
        lines.append(f"[错误] 找不到 SpaceNet8 根目录: {SPACENET8_ROOT}")
        REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return

    for dataset_name in DATASETS:
        dataset_root = SPACENET8_ROOT / dataset_name

        lines.append("=" * 80)
        lines.append(f"数据集: {dataset_name}")
        lines.append("=" * 80)
        lines.append(f"路径: {dataset_root}")

        if not dataset_root.exists():
            lines.append(f"[错误] 数据集目录不存在: {dataset_root}")
            lines.append("")
            continue

        annotations_dir = dataset_root / "annotations"
        pre_dir = dataset_root / "PRE-event"
        post_dir = dataset_root / "POST-event"

        lines.append("")
        lines.append("核心目录是否存在：")
        lines.append(f"annotations: {annotations_dir.exists()}  | {annotations_dir}")
        lines.append(f"PRE-event  : {pre_dir.exists()}  | {pre_dir}")
        lines.append(f"POST-event : {post_dir.exists()}  | {post_dir}")

        annotation_files = list_files(annotations_dir, exts=[".geojson"])
        pre_files = list_files(pre_dir, exts=IMAGE_EXTS)
        post_files = list_files(post_dir, exts=IMAGE_EXTS)

        lines.append("")
        lines.append("文件数量：")
        lines.append(f"geojson 标注数量 : {len(annotation_files)}")
        lines.append(f"PRE-event 图像数: {len(pre_files)}")
        lines.append(f"POST-event 图像数: {len(post_files)}")

        lines.append("")
        lines.append("根目录下表格/说明文件：")
        root_files = [p for p in dataset_root.iterdir() if p.is_file()]
        for p in sorted(root_files):
            lines.append(f"  {p.name}")

        lines.append("")
        lines.append("前 5 个 annotations 文件：")
        for p in annotation_files[:5]:
            lines.append(f"  {p.name}")

        lines.append("")
        lines.append("前 5 个 PRE-event 图像：")
        for p in pre_files[:5]:
            lines.append(f"  {p.name}")

        lines.append("")
        lines.append("前 5 个 POST-event 图像：")
        for p in post_files[:5]:
            lines.append(f"  {p.name}")

        if annotation_files:
            lines.append("")
            lines.append("geojson 内容预览：")

            preview = read_geojson_preview(annotation_files[0])

            lines.append(f"示例文件: {Path(preview['path']).name}")
            lines.append(f"读取成功: {preview['ok']}")
            lines.append(f"顶层 keys: {preview.get('top_keys')}")
            lines.append(f"features 数量: {preview.get('feature_count')}")
            lines.append(f"properties 字段: {preview.get('feature_property_keys')}")

            lines.append("")
            lines.append("前几个 properties 示例：")

            for idx, props in enumerate(preview.get("sample_properties", []), start=1):
                lines.append(f"  feature {idx}:")
                for k, v in props.items():
                    lines.append(f"    {k}: {v}")

        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("=" * 80)
    print("SpaceNet8 结构检查完成")
    print(f"报告路径: {REPORT_PATH}")
    print("=" * 80)

    print("\n".join(lines[:120]))


if __name__ == "__main__":
    main()
