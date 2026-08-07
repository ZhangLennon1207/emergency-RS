# -*- coding: utf-8 -*-
"""
25_make_spacenet8_road_status_dataset.py

作用：
将 SpaceNet8 Germany + Louisiana-East 的道路 geojson 标注转换成道路状态训练数据集。

输入：
data/SpaceNet8/
├── Germany_Training_Public/
│   ├── annotations/
│   ├── PRE-event/
│   ├── POST-event/
│   └── Germany_Training_Public_label_image_mapping.csv
│
├── Louisiana-East_Training_Public/
│   ├── annotations/
│   ├── PRE-event/
│   ├── POST-event/
│   └── Louisiana-East_Training_Public_label_image_mapping.csv

输出：
data/SpaceNet8/processed_road_status/
├── images_pre/
├── images_post/
├── masks_status/
├── masks_color/
├── preview/
├── splits/
└── metadata/

mask 类别：
0 = 背景 / 非道路
1 = 完好道路
2 = 受洪水影响道路

颜色：
0 = 黑色
1 = 白色
2 = 红色
"""

import os
import csv
import json
import random
from pathlib import Path
from collections import Counter

# ============================================================
# 0. Windows + conda 下修复 rasterio / GDAL / PROJ 路径
# 必须放在 import rasterio 之前
# ============================================================

CONDA_ENV_ROOT = os.environ.get("CONDA_PREFIX")
if CONDA_ENV_ROOT:
    GDAL_DATA_DIR = os.path.join(CONDA_ENV_ROOT, "Library", "share", "gdal")
    PROJ_DATA_DIR = os.path.join(CONDA_ENV_ROOT, "Library", "share", "proj")
    DLL_DIR = os.path.join(CONDA_ENV_ROOT, "Library", "bin")
    os.environ.setdefault("GDAL_DATA", GDAL_DATA_DIR)
    os.environ.setdefault("PROJ_LIB", PROJ_DATA_DIR)
    os.environ.setdefault("PROJ_DATA", PROJ_DATA_DIR)
    os.environ["PATH"] = DLL_DIR + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(DLL_DIR)

import numpy as np
from PIL import Image, ImageDraw

import rasterio
from rasterio.warp import transform_geom

from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

PROJECT_ROOT = workspace_root()

SPACENET8_ROOT = PROJECT_ROOT / "data" / "SpaceNet8"

DATASETS = [
    "Germany_Training_Public",
    "Louisiana-East_Training_Public",
]

OUTPUT_ROOT = SPACENET8_ROOT / "processed_road_status"

OUTPUT_PRE_DIR = OUTPUT_ROOT / "images_pre"
OUTPUT_POST_DIR = OUTPUT_ROOT / "images_post"
OUTPUT_MASK_DIR = OUTPUT_ROOT / "masks_status"
OUTPUT_COLOR_DIR = OUTPUT_ROOT / "masks_color"
OUTPUT_PREVIEW_DIR = OUTPUT_ROOT / "preview"
OUTPUT_SPLITS_DIR = OUTPUT_ROOT / "splits"
OUTPUT_METADATA_DIR = OUTPUT_ROOT / "metadata"

for p in [
    OUTPUT_ROOT,
    OUTPUT_PRE_DIR,
    OUTPUT_POST_DIR,
    OUTPUT_MASK_DIR,
    OUTPUT_COLOR_DIR,
    OUTPUT_PREVIEW_DIR,
    OUTPUT_SPLITS_DIR,
    OUTPUT_METADATA_DIR,
]:
    p.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. 参数设置
# ============================================================

# 输出图像统一尺寸
# 后面训练道路状态模型时，512 最方便，也和 EBD 当前图像尺寸一致
OUTPUT_SIZE = 512

# 是否处理 post-event image 2
# 有些样本有两个灾后图。开启后会把 post1、post2 都作为训练样本。
USE_POST_IMAGE_2 = True

# 调试时可以改成 50；正式生成改成 None
MAX_SAMPLES = None

# 随机种子
RANDOM_SEED = 42

# 数据集划分
TRAIN_RATIO = 0.8
VAL_RATIO = 0.1
TEST_RATIO = 0.1

# 预览图最多保存多少张
MAX_PREVIEW_SAVE = 120

# 道路线宽基础值
# SpaceNet8 的道路标注是矢量线，不是完整道路面，所以需要画成一定宽度
BASE_ROAD_WIDTH_AT_512 = 7

# 不同道路类型的线宽倍率
HIGHWAY_WIDTH_SCALE = {
    "motorway": 1.8,
    "trunk": 1.6,
    "primary": 1.5,
    "secondary": 1.3,
    "tertiary": 1.1,
    "residential": 1.0,
    "unclassified": 1.0,
    "secondary_link": 1.0,
    "primary_link": 1.0,
    "service": 0.8,
}


# ============================================================
# 3. 类别和颜色
# ============================================================

CLASS_NAMES = {
    0: "background",
    1: "road_intact",
    2: "road_flooded",
}

COLOR_MAP = {
    0: (0, 0, 0),        # 背景：黑色
    1: (255, 255, 255),  # 完好道路：白色
    2: (255, 0, 0),      # 受影响道路：红色
}


# ============================================================
# 4. 基础工具函数
# ============================================================

def find_mapping_csv(dataset_root):
    for p in dataset_root.glob("*.csv"):
        name = p.name.lower()
        if "label" in name and "mapping" in name:
            return p
    return None


def read_mapping_rows(mapping_csv):
    rows = []

    with open(mapping_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append(row)

    return rows


def find_file(dataset_root, subdir, filename):
    p = dataset_root / subdir / filename

    if p.exists():
        return p

    matches = list((dataset_root / subdir).rglob(filename))

    if matches:
        return matches[0]

    return None


def is_road_feature(props):
    highway = props.get("highway", None)
    return highway is not None and str(highway).strip() != ""


def is_flooded_feature(props):
    flooded = props.get("flooded", None)
    return str(flooded).strip().lower() == "yes"


def get_highway_type(props):
    highway = props.get("highway", None)

    if highway is None:
        return "unknown"

    s = str(highway).strip()

    if s == "":
        return "unknown"

    return s


def get_geojson_crs(data):
    """
    SpaceNet8 的 geojson 通常是经纬度坐标。
    默认按照 EPSG:4326 处理。
    """
    crs_info = data.get("crs", None)

    if isinstance(crs_info, dict):
        props = crs_info.get("properties", {})
        name = props.get("name", "")

        if isinstance(name, str):
            upper = name.upper()

            if "4326" in upper:
                return "EPSG:4326"

            if "CRS84" in upper:
                return "EPSG:4326"

    return "EPSG:4326"


def geometry_to_paths(geom):
    """
    将 GeoJSON geometry 转为若干条点序列。
    主要支持 LineString / MultiLineString。
    Polygon / MultiPolygon 作为兜底处理。
    """
    if geom is None:
        return []

    gtype = geom.get("type")
    coords = geom.get("coordinates")

    if coords is None:
        return []

    paths = []

    if gtype == "LineString":
        paths.append(coords)

    elif gtype == "MultiLineString":
        for line in coords:
            paths.append(line)

    elif gtype == "Polygon":
        for ring in coords:
            paths.append(ring)

    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                paths.append(ring)

    return paths


def transform_feature_geometry_to_dataset_crs(geom, src_crs, dst_crs):
    if geom is None:
        return None

    if dst_crs is None:
        return geom

    return transform_geom(
        src_crs=src_crs,
        dst_crs=dst_crs,
        geom=geom,
        precision=6,
    )


def geom_paths_to_pixel_paths(geom, dataset):
    """
    将已经转换到 dataset CRS 的几何坐标转为像素坐标。
    返回若干条 [(col,row), ...]。
    """
    paths = geometry_to_paths(geom)

    pixel_paths = []

    for path in paths:
        pts = []

        for pt in path:
            if len(pt) < 2:
                continue

            x = float(pt[0])
            y = float(pt[1])

            row, col = dataset.index(x, y)

            pts.append((float(col), float(row)))

        if len(pts) >= 2:
            pixel_paths.append(pts)

    return pixel_paths


def get_draw_width(highway_type, image_w, image_h):
    """
    根据原始图像大小和道路类型确定画线宽度。
    因为最后会 resize 到 512，所以原图越大，画线应适当更宽。
    """
    scale_size = max(image_w, image_h) / OUTPUT_SIZE

    highway_scale = HIGHWAY_WIDTH_SCALE.get(highway_type, 1.0)

    width = int(round(BASE_ROAD_WIDTH_AT_512 * scale_size * highway_scale))

    width = max(4, width)

    return width


def read_tif_as_rgb(path):
    """
    用 rasterio 读取 tif，转成 RGB uint8。
    兼容 uint8 / uint16 / float。
    """
    with rasterio.open(path) as src:
        if src.count >= 3:
            arr = src.read([1, 2, 3])
        elif src.count == 1:
            band = src.read(1)
            arr = np.stack([band, band, band], axis=0)
        else:
            raise ValueError(f"无法读取图像波段: {path}")

    arr = np.transpose(arr, (1, 2, 0)).astype(np.float32)

    if arr.max() <= 255 and arr.min() >= 0:
        return np.clip(arr, 0, 255).astype(np.uint8)

    out = np.zeros_like(arr, dtype=np.float32)

    for c in range(3):
        band = arr[:, :, c]
        valid = np.isfinite(band)

        if valid.sum() == 0:
            continue

        lo = np.percentile(band[valid], 2)
        hi = np.percentile(band[valid], 98)

        if hi <= lo:
            out[:, :, c] = 0
        else:
            out[:, :, c] = (band - lo) / (hi - lo) * 255

    out = np.clip(out, 0, 255).astype(np.uint8)

    return out


def resize_rgb(arr, size=OUTPUT_SIZE):
    img = Image.fromarray(arr.astype(np.uint8)).convert("RGB")
    img = img.resize((size, size), Image.BILINEAR)
    return np.array(img).astype(np.uint8)


def resize_mask(mask, size=OUTPUT_SIZE):
    img = Image.fromarray(mask.astype(np.uint8)).convert("L")
    img = img.resize((size, size), Image.NEAREST)
    return np.array(img).astype(np.uint8)


def mask_to_color(mask):
    h, w = mask.shape
    color = np.zeros((h, w, 3), dtype=np.uint8)

    for cls_id, rgb in COLOR_MAP.items():
        color[mask == cls_id] = rgb

    return color


def overlay_mask_on_image(image_rgb, mask, alpha=0.75):
    color = mask_to_color(mask)

    overlay = image_rgb.copy()

    area = mask > 0

    overlay[area] = (
        image_rgb[area] * (1 - alpha)
        + color[area] * alpha
    ).astype(np.uint8)

    return overlay


def make_preview(pre_rgb, post_rgb, mask, save_path):
    """
    生成 2x2 预览图：
    pre / post / mask color / overlay
    """
    w, h = OUTPUT_SIZE, OUTPUT_SIZE

    color = mask_to_color(mask)
    overlay = overlay_mask_on_image(post_rgb, mask)

    canvas = Image.new("RGB", (w * 2, h * 2), (0, 0, 0))

    canvas.paste(Image.fromarray(pre_rgb), (0, 0))
    canvas.paste(Image.fromarray(post_rgb), (w, 0))
    canvas.paste(Image.fromarray(color), (0, h))
    canvas.paste(Image.fromarray(overlay), (w, h))

    draw = ImageDraw.Draw(canvas)

    try:
        font = Image.truetype("simhei.ttf", 22)
    except Exception:
        font = None

    draw.text((10, 10), "Pre image", fill=(255, 255, 255), font=font)
    draw.text((w + 10, 10), "Post image", fill=(255, 255, 255), font=font)
    draw.text((10, h + 10), "Road status mask", fill=(255, 255, 255), font=font)
    draw.text((w + 10, h + 10), "Overlay", fill=(255, 255, 255), font=font)

    # 图例
    legend_x = w + 10
    legend_y = h + 45

    draw.rectangle([legend_x, legend_y, legend_x + 30, legend_y + 20], fill=(255, 255, 255))
    draw.text((legend_x + 40, legend_y), "Intact road", fill=(255, 255, 255), font=font)

    legend_y += 35
    draw.rectangle([legend_x, legend_y, legend_x + 30, legend_y + 20], fill=(255, 0, 0))
    draw.text((legend_x + 40, legend_y), "Flooded road", fill=(255, 255, 255), font=font)

    canvas.save(save_path)


# ============================================================
# 5. 生成道路状态 mask
# ============================================================

def rasterize_road_status_mask(post_tif_path, geojson_path):
    """
    生成原始尺寸道路状态 mask。

    规则：
    highway 不为空，且 flooded != yes → 1 完好道路
    highway 不为空，且 flooded == yes → 2 受影响道路

    优先级：
    受影响道路 class 2 覆盖完好道路 class 1。
    """
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    geojson_crs = get_geojson_crs(data)

    with rasterio.open(post_tif_path) as src:
        h = src.height
        w = src.width
        dst_crs = src.crs

        intact_layer = Image.new("L", (w, h), 0)
        flooded_layer = Image.new("L", (w, h), 0)

        draw_intact = ImageDraw.Draw(intact_layer)
        draw_flooded = ImageDraw.Draw(flooded_layer)

        road_feature_count = 0
        flooded_road_feature_count = 0
        drawn_road_feature_count = 0

        highway_counter = Counter()
        surface_counter = Counter()

        for feat in data.get("features", []):
            props = feat.get("properties", {})

            if not is_road_feature(props):
                continue

            road_feature_count += 1

            highway_type = get_highway_type(props)
            highway_counter[highway_type] += 1

            surface = props.get("surface", None)
            surface_counter[str(surface)] += 1

            flooded = is_flooded_feature(props)

            if flooded:
                flooded_road_feature_count += 1

            geom = feat.get("geometry", None)

            try:
                geom_dst = transform_feature_geometry_to_dataset_crs(
                    geom=geom,
                    src_crs=geojson_crs,
                    dst_crs=dst_crs,
                )

                pixel_paths = geom_paths_to_pixel_paths(
                    geom=geom_dst,
                    dataset=src,
                )

            except Exception:
                continue

            if not pixel_paths:
                continue

            width = get_draw_width(
                highway_type=highway_type,
                image_w=w,
                image_h=h,
            )

            for path in pixel_paths:
                if flooded:
                    draw_flooded.line(path, fill=255, width=width)
                else:
                    draw_intact.line(path, fill=255, width=width)

            drawn_road_feature_count += 1

    intact_arr = np.array(intact_layer).astype(np.uint8)
    flooded_arr = np.array(flooded_layer).astype(np.uint8)

    mask = np.zeros_like(intact_arr, dtype=np.uint8)

    # 先写完好道路
    mask[intact_arr > 0] = 1

    # 再写受影响道路，优先级更高
    mask[flooded_arr > 0] = 2

    info = {
        "road_feature_count": int(road_feature_count),
        "flooded_road_feature_count": int(flooded_road_feature_count),
        "drawn_road_feature_count": int(drawn_road_feature_count),
        "highway_counter": dict(highway_counter),
        "surface_counter": dict(surface_counter),
    }

    return mask, info


# ============================================================
# 6. 样本收集
# ============================================================

def collect_samples():
    samples = []

    for dataset_name in DATASETS:
        dataset_root = SPACENET8_ROOT / dataset_name
        mapping_csv = find_mapping_csv(dataset_root)

        if mapping_csv is None:
            print(f"[警告] 找不到 mapping CSV: {dataset_root}")
            continue

        rows = read_mapping_rows(mapping_csv)

        print(f"{dataset_name}: mapping rows = {len(rows)}")

        for row_idx, row in enumerate(rows):
            label_name = row.get("label", "").strip()
            pre_name = row.get("pre-event image", "").strip()
            post1_name = row.get("post-event image 1", "").strip()
            post2_name = row.get("post-event image 2", "").strip()

            if not label_name or not pre_name or not post1_name:
                continue

            label_path = find_file(dataset_root, "annotations", label_name)
            pre_path = find_file(dataset_root, "PRE-event", pre_name)

            if label_path is None or pre_path is None:
                continue

            post_candidates = []

            post1_path = find_file(dataset_root, "POST-event", post1_name)

            if post1_path is not None:
                post_candidates.append(("post1", post1_name, post1_path))

            if USE_POST_IMAGE_2 and post2_name:
                post2_path = find_file(dataset_root, "POST-event", post2_name)

                if post2_path is not None:
                    post_candidates.append(("post2", post2_name, post2_path))

            base_id = Path(label_name).stem

            for post_tag, post_name, post_path in post_candidates:
                sample_id = f"{dataset_name}_{base_id}_{post_tag}"

                samples.append({
                    "sample_id": sample_id,
                    "dataset_name": dataset_name,
                    "base_label_id": base_id,
                    "label_name": label_name,
                    "pre_name": pre_name,
                    "post_name": post_name,
                    "post_tag": post_tag,
                    "label_path": label_path,
                    "pre_path": pre_path,
                    "post_path": post_path,
                })

    samples = sorted(samples, key=lambda x: x["sample_id"])

    if MAX_SAMPLES is not None:
        samples = samples[:MAX_SAMPLES]

    return samples


def make_split_by_label(samples):
    """
    按 base_label_id 分组划分，避免同一 label 的 post1/post2 分到不同集合。
    """
    random.seed(RANDOM_SEED)

    label_keys = sorted(
        set((s["dataset_name"], s["base_label_id"]) for s in samples)
    )

    random.shuffle(label_keys)

    n = len(label_keys)

    n_train = int(n * TRAIN_RATIO)
    n_val = int(n * VAL_RATIO)

    train_keys = set(label_keys[:n_train])
    val_keys = set(label_keys[n_train:n_train + n_val])
    test_keys = set(label_keys[n_train + n_val:])

    split_map = {}

    for s in samples:
        key = (s["dataset_name"], s["base_label_id"])

        if key in train_keys:
            split = "train"
        elif key in val_keys:
            split = "val"
        else:
            split = "test"

        split_map[s["sample_id"]] = split

    return split_map


# ============================================================
# 7. 单样本处理
# ============================================================

def process_one_sample(sample, split, preview_index):
    sample_id = sample["sample_id"]

    pre_rgb_raw = read_tif_as_rgb(sample["pre_path"])
    post_rgb_raw = read_tif_as_rgb(sample["post_path"])

    mask_raw, raster_info = rasterize_road_status_mask(
        post_tif_path=sample["post_path"],
        geojson_path=sample["label_path"],
    )

    pre_rgb = resize_rgb(pre_rgb_raw, OUTPUT_SIZE)
    post_rgb = resize_rgb(post_rgb_raw, OUTPUT_SIZE)
    mask = resize_mask(mask_raw, OUTPUT_SIZE)

    color = mask_to_color(mask)

    pre_out = OUTPUT_PRE_DIR / f"{sample_id}_pre.png"
    post_out = OUTPUT_POST_DIR / f"{sample_id}_post.png"
    mask_out = OUTPUT_MASK_DIR / f"{sample_id}_road_status_mask.png"
    color_out = OUTPUT_COLOR_DIR / f"{sample_id}_road_status_color.png"

    Image.fromarray(pre_rgb).save(pre_out)
    Image.fromarray(post_rgb).save(post_out)
    Image.fromarray(mask).save(mask_out)
    Image.fromarray(color).save(color_out)

    preview_out = ""

    if preview_index < MAX_PREVIEW_SAVE:
        preview_path = OUTPUT_PREVIEW_DIR / f"{sample_id}_preview.png"
        make_preview(
            pre_rgb=pre_rgb,
            post_rgb=post_rgb,
            mask=mask,
            save_path=preview_path,
        )
        preview_out = str(preview_path)

    counts = {
        0: int((mask == 0).sum()),
        1: int((mask == 1).sum()),
        2: int((mask == 2).sum()),
    }

    total_pixels = int(mask.size)

    road_pixels = counts[1] + counts[2]
    flooded_ratio_in_road = 0.0

    if road_pixels > 0:
        flooded_ratio_in_road = counts[2] / road_pixels

    record = {
        "sample_id": sample_id,
        "split": split,
        "dataset_name": sample["dataset_name"],
        "base_label_id": sample["base_label_id"],
        "post_tag": sample["post_tag"],
        "label_name": sample["label_name"],
        "pre_name": sample["pre_name"],
        "post_name": sample["post_name"],
        "pre_path": str(sample["pre_path"]),
        "post_path": str(sample["post_path"]),
        "label_path": str(sample["label_path"]),
        "output_pre": str(pre_out),
        "output_post": str(post_out),
        "output_mask": str(mask_out),
        "output_color": str(color_out),
        "output_preview": preview_out,
        "background_pixels": counts[0],
        "road_intact_pixels": counts[1],
        "road_flooded_pixels": counts[2],
        "road_pixels": road_pixels,
        "flooded_ratio_in_road": float(flooded_ratio_in_road),
        "total_pixels": total_pixels,
        "road_feature_count": raster_info["road_feature_count"],
        "flooded_road_feature_count": raster_info["flooded_road_feature_count"],
        "drawn_road_feature_count": raster_info["drawn_road_feature_count"],
        "highway_counter_json": json.dumps(raster_info["highway_counter"], ensure_ascii=False),
        "surface_counter_json": json.dumps(raster_info["surface_counter"], ensure_ascii=False),
    }

    return record


# ============================================================
# 8. 保存 metadata 和 split
# ============================================================

def write_metadata_csv(records):
    metadata_csv = OUTPUT_METADATA_DIR / "spacenet8_road_status_metadata.csv"

    fieldnames = [
        "sample_id",
        "split",
        "dataset_name",
        "base_label_id",
        "post_tag",
        "label_name",
        "pre_name",
        "post_name",
        "pre_path",
        "post_path",
        "label_path",
        "output_pre",
        "output_post",
        "output_mask",
        "output_color",
        "output_preview",
        "background_pixels",
        "road_intact_pixels",
        "road_flooded_pixels",
        "road_pixels",
        "flooded_ratio_in_road",
        "total_pixels",
        "road_feature_count",
        "flooded_road_feature_count",
        "drawn_road_feature_count",
        "highway_counter_json",
        "surface_counter_json",
    ]

    with open(metadata_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in records:
            writer.writerow(r)

    return metadata_csv


def write_split_files(records):
    split_to_records = {
        "train": [],
        "val": [],
        "test": [],
    }

    for r in records:
        split_to_records[r["split"]].append(r)

    for split, items in split_to_records.items():
        split_path = OUTPUT_SPLITS_DIR / f"{split}.txt"

        with open(split_path, "w", encoding="utf-8") as f:
            for r in items:
                f.write(r["sample_id"] + "\n")

    return split_to_records


def write_summary_json(records):
    summary_path = OUTPUT_METADATA_DIR / "spacenet8_road_status_summary.json"

    split_counter = Counter(r["split"] for r in records)
    dataset_counter = Counter(r["dataset_name"] for r in records)

    total_road_pixels = sum(int(r["road_pixels"]) for r in records)
    total_flooded_pixels = sum(int(r["road_flooded_pixels"]) for r in records)
    total_intact_pixels = sum(int(r["road_intact_pixels"]) for r in records)

    total_road_features = sum(int(r["road_feature_count"]) for r in records)
    total_flooded_features = sum(int(r["flooded_road_feature_count"]) for r in records)

    summary = {
        "output_root": str(OUTPUT_ROOT),
        "output_size": OUTPUT_SIZE,
        "class_names": CLASS_NAMES,
        "class_colors": COLOR_MAP,
        "num_records": len(records),
        "split_counter": dict(split_counter),
        "dataset_counter": dict(dataset_counter),
        "total_road_pixels": int(total_road_pixels),
        "total_intact_road_pixels": int(total_intact_pixels),
        "total_flooded_road_pixels": int(total_flooded_pixels),
        "total_road_features": int(total_road_features),
        "total_flooded_road_features": int(total_flooded_features),
        "flooded_pixel_ratio_in_road": float(total_flooded_pixels / total_road_pixels) if total_road_pixels > 0 else 0.0,
        "train_ratio": TRAIN_RATIO,
        "val_ratio": VAL_RATIO,
        "test_ratio": TEST_RATIO,
        "random_seed": RANDOM_SEED,
        "use_post_image_2": USE_POST_IMAGE_2,
        "base_road_width_at_512": BASE_ROAD_WIDTH_AT_512,
    }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return summary_path, summary


# ============================================================
# 9. 主函数
# ============================================================

def main():
    print("=" * 100)
    print("SpaceNet8 道路状态训练数据集生成")
    print("=" * 100)
    print(f"rasterio version = {rasterio.__version__}")
    print(f"SPACENET8_ROOT = {SPACENET8_ROOT}")
    print(f"OUTPUT_ROOT = {OUTPUT_ROOT}")
    print(f"OUTPUT_SIZE = {OUTPUT_SIZE}")
    print(f"USE_POST_IMAGE_2 = {USE_POST_IMAGE_2}")
    print(f"MAX_SAMPLES = {MAX_SAMPLES}")
    print("=" * 100)

    samples = collect_samples()

    print(f"收集到样本数量: {len(samples)}")

    if len(samples) == 0:
        print("没有收集到样本，请检查 SpaceNet8 目录结构。")
        return

    split_map = make_split_by_label(samples)

    records = []

    for idx, sample in enumerate(samples):
        sample_id = sample["sample_id"]
        split = split_map[sample_id]

        print(f"[{idx + 1}/{len(samples)}] {sample_id} | split={split}")

        try:
            record = process_one_sample(
                sample=sample,
                split=split,
                preview_index=idx,
            )

            records.append(record)

            print(
                f"  road_pixels={record['road_pixels']}, "
                f"flooded_pixels={record['road_flooded_pixels']}, "
                f"flooded_ratio={record['flooded_ratio_in_road']:.4f}, "
                f"road_features={record['road_feature_count']}, "
                f"flooded_features={record['flooded_road_feature_count']}"
            )

        except Exception as e:
            print(f"  [错误] 处理失败: {sample_id}")
            print(f"  {e}")

    metadata_csv = write_metadata_csv(records)
    split_to_records = write_split_files(records)
    summary_path, summary = write_summary_json(records)

    print("=" * 100)
    print("SpaceNet8 道路状态训练数据集生成完成")
    print("=" * 100)
    print(f"有效样本数量: {len(records)}")
    print(f"metadata CSV: {metadata_csv}")
    print(f"summary JSON: {summary_path}")
    print(f"images_pre: {OUTPUT_PRE_DIR}")
    print(f"images_post: {OUTPUT_POST_DIR}")
    print(f"masks_status: {OUTPUT_MASK_DIR}")
    print(f"masks_color: {OUTPUT_COLOR_DIR}")
    print(f"preview: {OUTPUT_PREVIEW_DIR}")
    print(f"splits: {OUTPUT_SPLITS_DIR}")
    print("")
    print("划分数量：")
    for split in ["train", "val", "test"]:
        print(f"  {split}: {len(split_to_records[split])}")

    print("")
    print("汇总：")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("=" * 100)


if __name__ == "__main__":
    main()
