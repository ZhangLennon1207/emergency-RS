# -*- coding: utf-8 -*-
"""
04_check_training_data.py

作用：
训练前检查 train / val / test 数据是否正常。

检查内容：
1. csv 是否能读取；
2. 图像和 mask 文件是否存在；
3. 图像和 mask 是否能正常打开；
4. 图像尺寸是否为 512×512；
5. 灾前建筑二值 mask 像素值是否为 0 和 255；
6. 灾后损伤等级 mask 像素值是否为 0,1,2,3,4；
7. 统计损伤等级像素分布。

输出：
data/processed/splits/data_check_report.txt
"""

from pathlib import Path
import csv
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = workspace_root()

DATA_DIR = PROJECT_ROOT / "data" / "processed"
SPLIT_DIR = DATA_DIR / "splits"

TRAIN_CSV = SPLIT_DIR / "train.csv"
VAL_CSV = SPLIT_DIR / "val.csv"
TEST_CSV = SPLIT_DIR / "test.csv"

REPORT_PATH = SPLIT_DIR / "data_check_report.txt"


# ============================================================
# 2. 检查参数
# ============================================================

EXPECTED_IMAGE_SIZE = (512, 512)

# 建筑二值 mask 像素值：0 = 背景，255 = 建筑物
EXPECTED_BUILDING_VALUES = {0, 255}

# 损伤等级 mask 像素值：
# 0 = 背景，1 = 无损，2 = 轻微损伤，3 = 严重损伤，4 = 摧毁
EXPECTED_DAMAGE_VALUES = {0, 1, 2, 3, 4}

DAMAGE_NAMES = {
    0: "background",
    1: "no_damage",
    2: "minor_damage",
    3: "major_damage",
    4: "destroyed",
}


# ============================================================
# 3. 工具函数
# ============================================================

def read_csv_records(csv_path):
    """读取 csv 文件"""
    if not csv_path.exists():
        raise FileNotFoundError(f"找不到文件：{csv_path}")

    records = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    return records


def open_rgb_image(path):
    """读取 RGB 图像"""
    return Image.open(path).convert("RGB")


def open_gray_mask(path):
    """读取灰度 mask"""
    return Image.open(path).convert("L")


def get_unique_values(mask_img):
    """统计 mask 中出现过的唯一像素值"""
    arr = np.array(mask_img)
    return set(np.unique(arr).astype(int).tolist())


def update_damage_pixel_counter(counter, damage_mask_img):
    """统计损伤等级像素数量"""
    arr = np.array(damage_mask_img)

    for cls_id in range(5):
        counter[cls_id] += int(np.sum(arr == cls_id))


# ============================================================
# 4. 检查单个 split
# ============================================================

def check_split(split_name, csv_path):
    records = read_csv_records(csv_path)

    result = {
        "split_name": split_name,
        "total": len(records),
        "missing_file_errors": [],
        "open_errors": [],
        "size_errors": [],
        "building_value_errors": [],
        "damage_value_errors": [],
        "disaster_counter": Counter(),
        "building_value_counter": Counter(),
        "damage_value_counter": Counter(),
        "damage_pixel_counter": defaultdict(int),
    }

    print("=" * 60)
    print(f"开始检查 {split_name}: {csv_path}")
    print(f"样本数：{len(records)}")
    print("=" * 60)

    required_cols = [
        "sample_id",
        "disaster_type",
        "pre_image",
        "post_image",
        "pre_building_mask",
        "post_damage_mask",
    ]

    if len(records) > 0:
        for col in required_cols:
            if col not in records[0]:
                raise ValueError(f"{csv_path} 缺少字段：{col}")

    for idx, row in enumerate(records):
        sample_id = row["sample_id"]
        disaster_type = row["disaster_type"]

        result["disaster_counter"][disaster_type] += 1

        paths = {
            "pre_image": DATA_DIR / row["pre_image"],
            "post_image": DATA_DIR / row["post_image"],
            "pre_building_mask": DATA_DIR / row["pre_building_mask"],
            "post_damage_mask": DATA_DIR / row["post_damage_mask"],
        }

        # 1. 检查文件是否存在
        for key, path in paths.items():
            if not path.exists():
                result["missing_file_errors"].append(
                    f"{sample_id}: 缺少 {key} -> {path}"
                )

        if any(not p.exists() for p in paths.values()):
            continue

        # 2. 检查文件是否能打开
        try:
            pre_img = open_rgb_image(paths["pre_image"])
            post_img = open_rgb_image(paths["post_image"])
            building_mask = open_gray_mask(paths["pre_building_mask"])
            damage_mask = open_gray_mask(paths["post_damage_mask"])
        except Exception as e:
            result["open_errors"].append(f"{sample_id}: 打开文件失败 -> {e}")
            continue

        # 3. 检查尺寸
        size_items = {
            "pre_image": pre_img.size,
            "post_image": post_img.size,
            "pre_building_mask": building_mask.size,
            "post_damage_mask": damage_mask.size,
        }

        for key, size in size_items.items():
            if size != EXPECTED_IMAGE_SIZE:
                result["size_errors"].append(
                    f"{sample_id}: {key} 尺寸为 {size}, 不是 {EXPECTED_IMAGE_SIZE}"
                )

        # 4. 检查建筑二值 mask 像素值
        building_values = get_unique_values(building_mask)

        for v in building_values:
            result["building_value_counter"][v] += 1

        if not building_values.issubset(EXPECTED_BUILDING_VALUES):
            result["building_value_errors"].append(
                f"{sample_id}: building_mask 像素值为 {sorted(building_values)}"
            )

        # 5. 检查损伤等级 mask 像素值
        damage_values = get_unique_values(damage_mask)

        for v in damage_values:
            result["damage_value_counter"][v] += 1

        if not damage_values.issubset(EXPECTED_DAMAGE_VALUES):
            result["damage_value_errors"].append(
                f"{sample_id}: damage_mask 像素值为 {sorted(damage_values)}"
            )

        # 6. 统计损伤等级像素数量
        update_damage_pixel_counter(result["damage_pixel_counter"], damage_mask)

        if (idx + 1) % 1000 == 0:
            print(f"{split_name}: 已检查 {idx + 1}/{len(records)}")

    return result


# ============================================================
# 5. 写检查报告
# ============================================================

def write_report(results):
    lines = []

    lines.append("训练前数据检查报告")
    lines.append("=" * 70)
    lines.append(f"项目根目录：{PROJECT_ROOT}")
    lines.append(f"数据目录：{DATA_DIR}")
    lines.append(f"期望图像尺寸：{EXPECTED_IMAGE_SIZE}")
    lines.append(f"期望建筑 mask 像素值：{sorted(EXPECTED_BUILDING_VALUES)}")
    lines.append(f"期望损伤 mask 像素值：{sorted(EXPECTED_DAMAGE_VALUES)}")
    lines.append("")

    total_all = sum(r["total"] for r in results)

    total_missing = sum(len(r["missing_file_errors"]) for r in results)
    total_open = sum(len(r["open_errors"]) for r in results)
    total_size = sum(len(r["size_errors"]) for r in results)
    total_building_value = sum(len(r["building_value_errors"]) for r in results)
    total_damage_value = sum(len(r["damage_value_errors"]) for r in results)

    lines.append("总体结果")
    lines.append("-" * 70)
    lines.append(f"总样本数：{total_all}")
    lines.append(f"缺失文件错误数：{total_missing}")
    lines.append(f"文件打开错误数：{total_open}")
    lines.append(f"尺寸异常数：{total_size}")
    lines.append(f"建筑 mask 像素值异常数：{total_building_value}")
    lines.append(f"损伤 mask 像素值异常数：{total_damage_value}")
    lines.append("")

    if (
        total_missing == 0
        and total_open == 0
        and total_size == 0
        and total_building_value == 0
        and total_damage_value == 0
    ):
        lines.append("结论：数据检查通过，可以进入模型训练阶段。")
    else:
        lines.append("结论：数据存在异常，请先根据下方错误信息修正后再训练。")

    lines.append("")
    lines.append("=" * 70)

    for r in results:
        split_name = r["split_name"]

        lines.append("")
        lines.append(f"{split_name} 检查结果")
        lines.append("-" * 70)
        lines.append(f"样本数：{r['total']}")
        lines.append(f"缺失文件错误数：{len(r['missing_file_errors'])}")
        lines.append(f"文件打开错误数：{len(r['open_errors'])}")
        lines.append(f"尺寸异常数：{len(r['size_errors'])}")
        lines.append(f"建筑 mask 像素值异常数：{len(r['building_value_errors'])}")
        lines.append(f"损伤 mask 像素值异常数：{len(r['damage_value_errors'])}")
        lines.append("")

        lines.append("各灾害类型样本数：")
        for k, v in sorted(r["disaster_counter"].items()):
            lines.append(f"  {k}: {v}")
        lines.append("")

        lines.append("建筑 mask 出现过的像素值：")
        for k, v in sorted(r["building_value_counter"].items()):
            lines.append(f"  像素值 {k}: 出现在 {v} 个样本中")
        lines.append("")

        lines.append("损伤 mask 出现过的像素值：")
        for k, v in sorted(r["damage_value_counter"].items()):
            lines.append(f"  像素值 {k}: 出现在 {v} 个样本中")
        lines.append("")

        lines.append("损伤等级像素数量统计：")
        total_pixels = sum(r["damage_pixel_counter"].values())

        for cls_id in range(5):
            count = r["damage_pixel_counter"][cls_id]
            ratio = count / total_pixels if total_pixels > 0 else 0
            lines.append(
                f"  {cls_id}({DAMAGE_NAMES[cls_id]}): {count} 像素，占比 {ratio:.6f}"
            )

        error_sections = [
            ("缺失文件错误", r["missing_file_errors"]),
            ("文件打开错误", r["open_errors"]),
            ("尺寸异常", r["size_errors"]),
            ("建筑 mask 像素值异常", r["building_value_errors"]),
            ("损伤 mask 像素值异常", r["damage_value_errors"]),
        ]

        for title, errors in error_sections:
            if len(errors) > 0:
                lines.append("")
                lines.append(f"{title}，前 50 条：")
                for e in errors[:50]:
                    lines.append(f"  {e}")
                if len(errors) > 50:
                    lines.append(f"  ... 其余 {len(errors) - 50} 条省略")

        lines.append("")
        lines.append("=" * 70)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================
# 6. 主程序
# ============================================================

def main():
    print("=" * 60)
    print("训练前数据检查开始")
    print("=" * 60)

    split_files = [
        ("train", TRAIN_CSV),
        ("val", VAL_CSV),
        ("test", TEST_CSV),
    ]

    results = []

    for split_name, csv_path in split_files:
        result = check_split(split_name, csv_path)
        results.append(result)

    write_report(results)

    print("=" * 60)
    print("训练前数据检查完成")
    print(f"检查报告：{REPORT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
