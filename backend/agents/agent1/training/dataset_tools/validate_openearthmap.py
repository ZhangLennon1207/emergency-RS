# -*- coding: utf-8 -*-
"""
11_check_openearthmap_data.py

作用：
1. 检查 OpenEarthMap_wo_xBD 的目录结构；
2. 自动寻找每个城市文件夹下的 images 和 labels/masks；
3. 统计图片和标签数量；
4. 随机读取几张标签，查看标签是单通道类别图还是 RGB 彩色标签图；
5. 为后续 4 类地物分割训练做准备。

当前目标类别：
0 = 背景/其他
1 = 农田 agriculture land
2 = 道路 road
3 = 建筑 building
"""

from pathlib import Path
from PIL import Image
import numpy as np
import random

from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

PROJECT_ROOT = workspace_root()

RAW_ROOT = (
    PROJECT_ROOT
    / "data"
    / "openearthmap"
    / "raw"
    / "OpenEarthMap_wo_xBD"
)

print("=" * 80)
print("OpenEarthMap 数据检查")
print("=" * 80)
print(f"RAW_ROOT = {RAW_ROOT}")
print("=" * 80)


# ============================================================
# 2. 检查根目录
# ============================================================

if not RAW_ROOT.exists():
    raise FileNotFoundError(
        f"找不到 OpenEarthMap_wo_xBD 目录：{RAW_ROOT}\n"
        f"请检查 PROJECT_ROOT 或 RAW_ROOT 是否写错。"
    )

city_dirs = sorted([p for p in RAW_ROOT.iterdir() if p.is_dir()])

print(f"发现城市/区域文件夹数量：{len(city_dirs)}")
print("前 10 个文件夹：")
for p in city_dirs[:10]:
    print("  ", p.name)

print("=" * 80)


# ============================================================
# 3. 自动查找 images 和 labels/masks
# ============================================================

all_pairs = []
label_examples = []

possible_label_names = [
    "labels",
    "label",
    "masks",
    "mask",
    "annotations",
    "annotation",
]

for city_dir in city_dirs:
    image_dir = city_dir / "images"

    if not image_dir.exists():
        print(f"[跳过] {city_dir.name} 没有 images 文件夹")
        continue

    label_dir = None
    for name in possible_label_names:
        candidate = city_dir / name
        if candidate.exists():
            label_dir = candidate
            break

    if label_dir is None:
        print(f"[注意] {city_dir.name} 有 images，但没有找到 labels/masks 文件夹")
        continue

    image_files = sorted(
        list(image_dir.glob("*.tif"))
        + list(image_dir.glob("*.tiff"))
        + list(image_dir.glob("*.png"))
        + list(image_dir.glob("*.jpg"))
    )

    label_files = sorted(
        list(label_dir.glob("*.tif"))
        + list(label_dir.glob("*.tiff"))
        + list(label_dir.glob("*.png"))
        + list(label_dir.glob("*.jpg"))
    )

    print(f"[{city_dir.name}] images={len(image_files)}, labels={len(label_files)}, label_dir={label_dir.name}")

    # 按文件名 stem 配对
    label_dict = {p.stem: p for p in label_files}

    for img_path in image_files:
        stem = img_path.stem
        if stem in label_dict:
            all_pairs.append((img_path, label_dict[stem], city_dir.name))
            if len(label_examples) < 10:
                label_examples.append(label_dict[stem])

print("=" * 80)
print(f"成功配对 image-label 数量：{len(all_pairs)}")
print("=" * 80)


# ============================================================
# 4. 检查标签格式
# ============================================================

if len(label_examples) == 0:
    print("没有找到可用标签样本。请截图一个城市文件夹内部结构给我看。")
else:
    sample_labels = random.sample(label_examples, min(5, len(label_examples)))

    for label_path in sample_labels:
        print(f"\n检查标签：{label_path}")

        mask = Image.open(label_path)
        arr = np.array(mask)

        print(f"  shape = {arr.shape}")
        print(f"  dtype = {arr.dtype}")

        if arr.ndim == 2:
            unique_vals = np.unique(arr)
            print(f"  单通道标签，唯一值数量 = {len(unique_vals)}")
            print(f"  唯一值前 50 个 = {unique_vals[:50].tolist()}")

        elif arr.ndim == 3:
            h, w, c = arr.shape
            flat = arr.reshape(-1, c)
            unique_colors = np.unique(flat, axis=0)
            print(f"  RGB/RGBA 标签，通道数 = {c}")
            print(f"  唯一颜色数量 = {len(unique_colors)}")
            print(f"  唯一颜色前 30 个：")
            for color in unique_colors[:30]:
                print("   ", color.tolist())

        else:
            print("  未知标签格式")

print("\n检查完成。")
print("=" * 80)
