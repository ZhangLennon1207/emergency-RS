# -*- coding: utf-8 -*-
"""
12_make_openearthmap_road_dataset.py

作用：
1. 读取 OpenEarthMap_wo_xBD 原始 image-label 配对；
2. 将 OpenEarthMap 原 0~8 标签重映射为道路二值标签：
   0 = 背景/其他
   1 = 道路
3. 生成 masks_road；
4. 生成彩色预览图；
5. 生成 train/val/test 划分 CSV。

说明：
- 这里只做道路二值分割；
- 建筑不再由 OpenEarthMap 这条线负责；
- 建筑继续使用你原来的 building_unet_medium_best.pth。
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import csv
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

PROCESSED_ROOT = (
    PROJECT_ROOT
    / "data"
    / "openearthmap"
    / "processed"
)

MASK_ROAD_DIR = PROCESSED_ROOT / "masks_road"
COLOR_PREVIEW_DIR = PROCESSED_ROOT / "color_preview"
SPLITS_DIR = PROCESSED_ROOT / "splits"

MASK_ROAD_DIR.mkdir(parents=True, exist_ok=True)
COLOR_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
SPLITS_DIR.mkdir(parents=True, exist_ok=True)

METADATA_CSV = PROCESSED_ROOT / "openearthmap_road_metadata.csv"
TRAIN_CSV = SPLITS_DIR / "train.csv"
VAL_CSV = SPLITS_DIR / "val.csv"
TEST_CSV = SPLITS_DIR / "test.csv"


# ============================================================
# 2. 类别映射
# ============================================================

"""
OpenEarthMap 原标签：
0 = background / unlabeled
1 = bareland
2 = rangeland
3 = developed space
4 = road
5 = tree
6 = water
7 = agriculture land
8 = building

道路二值标签：
0 = 背景/其他
1 = 道路
"""

OEM_TO_ROAD_BINARY = {
    0: 0,
    1: 0,
    2: 0,
    3: 0,
    4: 1,  # road
    5: 0,
    6: 0,
    7: 0,
    8: 0,
}

CLASS_NAMES_CN = {
    0: "背景/其他",
    1: "道路",
}

CLASS_COLORS = {
    0: (0, 0, 0),          # 背景：黑色
    1: (255, 255, 255),    # 道路：白色
}


# ============================================================
# 3. 工具函数
# ============================================================

def remap_to_road_binary(mask_arr):
    out = np.zeros_like(mask_arr, dtype=np.uint8)

    for old_id, new_id in OEM_TO_ROAD_BINARY.items():
        out[mask_arr == old_id] = new_id

    return out


def mask_to_color(mask_bin):
    h, w = mask_bin.shape
    color = np.zeros((h, w, 3), dtype=np.uint8)

    for class_id, rgb in CLASS_COLORS.items():
        color[mask_bin == class_id] = rgb

    return color


def add_legend_to_color_image(color_img):
    img = Image.fromarray(color_img).convert("RGB")
    w, h = img.size

    legend_w = 260
    canvas = Image.new("RGB", (w + legend_w, h), (245, 245, 245))
    canvas.paste(img, (0, 0))

    draw = ImageDraw.Draw(canvas)

    try:
        font_title = ImageFont.truetype("simhei.ttf", 24)
        font = ImageFont.truetype("simhei.ttf", 20)
    except Exception:
        font_title = ImageFont.load_default()
        font = ImageFont.load_default()

    x0 = w + 25
    y = 40

    draw.text((x0, y), "道路类别图例", fill=(0, 0, 0), font=font_title)
    y += 50

    for class_id in [0, 1]:
        color = CLASS_COLORS[class_id]
        name = CLASS_NAMES_CN[class_id]

        draw.rectangle([x0, y, x0 + 32, y + 24], fill=color, outline=(0, 0, 0))
        draw.text((x0 + 45, y), f"{class_id}  {name}", fill=(0, 0, 0), font=font)
        y += 45

    return canvas


def find_pairs():
    all_pairs = []

    city_dirs = sorted([p for p in RAW_ROOT.iterdir() if p.is_dir()])

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
            continue

        label_dir = None
        for name in possible_label_names:
            candidate = city_dir / name
            if candidate.exists():
                label_dir = candidate
                break

        if label_dir is None:
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

        label_dict = {p.stem: p for p in label_files}

        for img_path in image_files:
            stem = img_path.stem
            if stem in label_dict:
                all_pairs.append({
                    "region": city_dir.name,
                    "stem": stem,
                    "image_path": img_path,
                    "label_path": label_dict[stem],
                })

    return all_pairs


def save_csv(rows, path):
    fieldnames = [
        "region",
        "stem",
        "image_path",
        "original_label_path",
        "mask_road_path",
    ]

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                "region": row["region"],
                "stem": row["stem"],
                "image_path": str(row["image_path"]).replace("\\", "/"),
                "original_label_path": str(row["label_path"]).replace("\\", "/"),
                "mask_road_path": str(row["mask_road_path"]).replace("\\", "/"),
            })


# ============================================================
# 4. 主程序
# ============================================================

def main():
    print("=" * 80)
    print("OpenEarthMap 道路二值数据集生成")
    print("=" * 80)
    print(f"RAW_ROOT = {RAW_ROOT}")
    print(f"PROCESSED_ROOT = {PROCESSED_ROOT}")
    print("=" * 80)

    if not RAW_ROOT.exists():
        raise FileNotFoundError(f"找不到 RAW_ROOT：{RAW_ROOT}")

    pairs = find_pairs()

    print(f"找到 image-label 配对数量：{len(pairs)}")

    if len(pairs) == 0:
        print("没有找到可用配对，请检查目录结构。")
        return

    processed_rows = []

    class_pixel_count = {
        0: 0,
        1: 0,
    }

    for idx, item in enumerate(pairs, start=1):
        region = item["region"]
        stem = item["stem"]
        label_path = item["label_path"]

        if idx == 1 or idx % 100 == 0:
            print(f"[{idx}/{len(pairs)}] 处理：{region}/{stem}")

        label = Image.open(label_path)
        label_arr = np.array(label)

        if label_arr.ndim != 2:
            print(f"[跳过] 标签不是单通道：{label_path}, shape={label_arr.shape}")
            continue

        mask_road = remap_to_road_binary(label_arr)

        out_name = f"{region}_{stem}_road.png"
        mask_out_path = MASK_ROAD_DIR / out_name
        Image.fromarray(mask_road).save(mask_out_path)

        unique, counts = np.unique(mask_road, return_counts=True)
        for u, c in zip(unique, counts):
            class_pixel_count[int(u)] += int(c)

        # 前 60 张生成预览图
        if idx <= 60:
            color = mask_to_color(mask_road)
            color_with_legend = add_legend_to_color_image(color)
            preview_path = COLOR_PREVIEW_DIR / f"{region}_{stem}_road_color_legend.png"
            color_with_legend.save(preview_path)

        new_item = dict(item)
        new_item["mask_road_path"] = mask_out_path
        processed_rows.append(new_item)

    print("=" * 80)
    print(f"成功生成道路 mask 数量：{len(processed_rows)}")
    print("道路二值像素统计：")

    total_pixels = sum(class_pixel_count.values())

    for class_id in [0, 1]:
        count = class_pixel_count[class_id]
        ratio = count / total_pixels if total_pixels > 0 else 0
        print(f"  {class_id} {CLASS_NAMES_CN[class_id]}: {count} 像素，占比 {ratio * 100:.2f}%")

    save_csv(processed_rows, METADATA_CSV)
    print(f"metadata 保存到：{METADATA_CSV}")

    random.seed(42)
    random.shuffle(processed_rows)

    n = len(processed_rows)
    n_train = int(n * 0.7)
    n_val = int(n * 0.15)

    train_rows = processed_rows[:n_train]
    val_rows = processed_rows[n_train:n_train + n_val]
    test_rows = processed_rows[n_train + n_val:]

    save_csv(train_rows, TRAIN_CSV)
    save_csv(val_rows, VAL_CSV)
    save_csv(test_rows, TEST_CSV)

    print("=" * 80)
    print("数据集划分完成：")
    print(f"  train: {len(train_rows)} -> {TRAIN_CSV}")
    print(f"  val:   {len(val_rows)} -> {VAL_CSV}")
    print(f"  test:  {len(test_rows)} -> {TEST_CSV}")
    print("=" * 80)
    print(f"彩色预览图保存位置：{COLOR_PREVIEW_DIR}")
    print("请打开前几张 *_road_color_legend.png 检查道路是否为白色。")
    print("=" * 80)


if __name__ == "__main__":
    main()
