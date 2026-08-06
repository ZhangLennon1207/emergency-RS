# -*- coding: utf-8 -*-
"""
01_make_metadata.py

作用：
1. 扫描 data/processed/images 里的灾前/灾后遥感图像
2. 扫描 data/processed/masks 里的灾前/灾后掩码图
3. 按 sample_id 自动配对
4. 生成 data/processed/metadata.csv
5. 生成 data/processed/metadata_check_report.txt 检查报告

说明：
- xxx_pre_disaster.png 认为是灾前图 / 灾前建筑物二值掩码
- xxx_post_disaster.png 认为是灾后图 / 灾后损伤等级掩码
"""

from pathlib import Path
import csv

from backend.agents.agent1.training.config import workspace_root

# ============================================================
# 1. 自动定位项目根目录
# 当前脚本位置：
# DisasterAgent_Project/agent1_visual_evidence/scripts/01_make_metadata.py
# 所以 parents[2] 就是 DisasterAgent_Project
# ============================================================

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = workspace_root()

DATA_DIR = PROJECT_ROOT / "data" / "processed"
IMAGES_DIR = DATA_DIR / "images"
MASKS_DIR = DATA_DIR / "masks"

OUT_CSV = DATA_DIR / "metadata.csv"
OUT_REPORT = DATA_DIR / "metadata_check_report.txt"

# 支持的图片后缀
IMG_SUFFIXES = [".png", ".jpg", ".jpeg", ".tif", ".tiff"]


def is_image_file(path):
    """判断是否为图片文件"""
    return path.is_file() and path.suffix.lower() in IMG_SUFFIXES


def get_sample_id(filename):
    """
    从文件名中提取 sample_id
    例如：
    EARTHQUAKE-TURKEY_000013_pre_disaster.png
    -> EARTHQUAKE-TURKEY_000013
    """
    stem = Path(filename).stem

    if stem.endswith("_pre_disaster"):
        return stem.replace("_pre_disaster", "")
    elif stem.endswith("_post_disaster"):
        return stem.replace("_post_disaster", "")
    else:
        return None


def get_time_type(filename):
    """
    判断是 pre 还是 post
    """
    stem = Path(filename).stem

    if stem.endswith("_pre_disaster"):
        return "pre"
    elif stem.endswith("_post_disaster"):
        return "post"
    else:
        return None


def get_disaster_type(file_path, root_dir):
    """
    根据子文件夹名提取灾害类型
    例如：
    data/processed/images/EARTHQUAKE-TURKEY/xxx.png
    -> EARTHQUAKE-TURKEY
    """
    rel = file_path.relative_to(root_dir)
    parts = rel.parts

    if len(parts) >= 2:
        return parts[0]
    else:
        # 如果文件直接放在 images 下面，就尝试从文件名前缀提取
        sample_id = get_sample_id(file_path.name)
        if sample_id is not None:
            # 例如 EARTHQUAKE-TURKEY_000013 -> EARTHQUAKE-TURKEY
            return sample_id.rsplit("_", 1)[0]
        return "UNKNOWN"


def to_rel_path(path):
    """
    转成相对于 data/processed 的路径，方便写入 metadata.csv
    """
    return path.relative_to(DATA_DIR).as_posix()


# ============================================================
# 2. 扫描 images
# ============================================================

image_dict = {}

for img_path in IMAGES_DIR.rglob("*"):
    if not is_image_file(img_path):
        continue

    sample_id = get_sample_id(img_path.name)
    time_type = get_time_type(img_path.name)

    if sample_id is None or time_type is None:
        continue

    disaster_type = get_disaster_type(img_path, IMAGES_DIR)

    if sample_id not in image_dict:
        image_dict[sample_id] = {
            "sample_id": sample_id,
            "disaster_type": disaster_type,
            "pre_image": "",
            "post_image": "",
        }

    if time_type == "pre":
        image_dict[sample_id]["pre_image"] = to_rel_path(img_path)
    elif time_type == "post":
        image_dict[sample_id]["post_image"] = to_rel_path(img_path)


# ============================================================
# 3. 扫描 masks
# ============================================================

mask_dict = {}

for mask_path in MASKS_DIR.rglob("*"):
    if not is_image_file(mask_path):
        continue

    sample_id = get_sample_id(mask_path.name)
    time_type = get_time_type(mask_path.name)

    if sample_id is None or time_type is None:
        continue

    if sample_id not in mask_dict:
        mask_dict[sample_id] = {
            "pre_building_mask": "",
            "post_damage_mask": "",
        }

    # 约定：
    # pre_disaster mask = 灾前建筑物二值掩码
    # post_disaster mask = 灾后建筑物损伤等级掩码
    if time_type == "pre":
        mask_dict[sample_id]["pre_building_mask"] = to_rel_path(mask_path)
    elif time_type == "post":
        mask_dict[sample_id]["post_damage_mask"] = to_rel_path(mask_path)


# ============================================================
# 4. 合并 images 和 masks，生成 metadata
# ============================================================

records = []
missing_records = []

for sample_id, img_info in sorted(image_dict.items()):
    pre_image = img_info["pre_image"]
    post_image = img_info["post_image"]

    mask_info = mask_dict.get(sample_id, {})
    pre_building_mask = mask_info.get("pre_building_mask", "")
    post_damage_mask = mask_info.get("post_damage_mask", "")

    record = {
        "sample_id": sample_id,
        "disaster_type": img_info["disaster_type"],
        "pre_image": pre_image,
        "post_image": post_image,
        "pre_building_mask": pre_building_mask,
        "post_damage_mask": post_damage_mask,
    }

    records.append(record)

    # 检查是否缺文件
    missing = []
    if pre_image == "":
        missing.append("pre_image")
    if post_image == "":
        missing.append("post_image")
    if pre_building_mask == "":
        missing.append("pre_building_mask")
    if post_damage_mask == "":
        missing.append("post_damage_mask")

    if missing:
        missing_records.append((sample_id, missing))


# ============================================================
# 5. 写出 metadata.csv
# ============================================================

headers = [
    "sample_id",
    "disaster_type",
    "pre_image",
    "post_image",
    "pre_building_mask",
    "post_damage_mask",
]

with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    for record in records:
        writer.writerow(record)


# ============================================================
# 6. 写出检查报告
# ============================================================

disaster_count = {}

for record in records:
    disaster_type = record["disaster_type"]
    disaster_count[disaster_type] = disaster_count.get(disaster_type, 0) + 1

with open(OUT_REPORT, "w", encoding="utf-8") as f:
    f.write("metadata 生成检查报告\n")
    f.write("=" * 60 + "\n\n")

    f.write(f"项目根目录：{PROJECT_ROOT}\n")
    f.write(f"images 目录：{IMAGES_DIR}\n")
    f.write(f"masks 目录：{MASKS_DIR}\n")
    f.write(f"metadata 输出：{OUT_CSV}\n\n")

    f.write(f"总样本数：{len(records)}\n")
    f.write(f"存在缺失的样本数：{len(missing_records)}\n\n")

    f.write("各灾害类型样本数：\n")
    for disaster_type, count in sorted(disaster_count.items()):
        f.write(f"  {disaster_type}: {count}\n")

    f.write("\n缺失文件样本列表：\n")
    if len(missing_records) == 0:
        f.write("  无缺失，配对正常。\n")
    else:
        for sample_id, missing in missing_records:
            f.write(f"  {sample_id}: 缺少 {', '.join(missing)}\n")


# ============================================================
# 7. 控制台输出
# ============================================================

print("=" * 60)
print("metadata.csv 生成完成")
print("=" * 60)
print(f"总样本数：{len(records)}")
print(f"存在缺失的样本数：{len(missing_records)}")
print(f"输出文件：{OUT_CSV}")
print(f"检查报告：{OUT_REPORT}")
print("=" * 60)

if len(missing_records) > 0:
    print("注意：存在缺失文件，请打开 metadata_check_report.txt 查看。")
else:
    print("所有样本配对正常。")
