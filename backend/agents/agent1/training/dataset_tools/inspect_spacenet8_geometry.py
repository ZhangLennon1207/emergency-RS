# -*- coding: utf-8 -*-
"""
24_check_spacenet8_geometry_rasterio.py
"""

import os
import sys

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

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import rasterio
from rasterio.warp import transform_geom

from backend.agents.agent1.training.config import workspace_root

print("rasterio import OK:", rasterio.__version__)

# ============================================================
# 1. 路径设置
# ============================================================

PROJECT_ROOT = workspace_root()

SPACENET8_ROOT = PROJECT_ROOT / "data" / "SpaceNet8"

DATASETS = [
    "Germany_Training_Public",
    "Louisiana-East_Training_Public",
]

OUTPUT_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "outputs" / "spacenet8_check"
PREVIEW_DIR = OUTPUT_DIR / "geometry_preview_rasterio"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

REPORT_PATH = OUTPUT_DIR / "geometry_check_report_rasterio.txt"

MAX_PREVIEW_PER_DATASET = 8


# ============================================================
# 2. 工具函数
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


def get_geojson_crs(data):
    """
    SpaceNet8 的 geojson 通常是经纬度坐标。
    如果 crs 字段能读取，就尝试读取；否则默认 EPSG:4326。

    注意：
    CRS84 和 EPSG:4326 在这里都可按 lon,lat 使用。
    """
    crs_info = data.get("crs", None)

    if isinstance(crs_info, dict):
        props = crs_info.get("properties", {})
        name = props.get("name", "")

        if isinstance(name, str) and name:
            if "4326" in name:
                return "EPSG:4326"
            if "CRS84" in name.upper():
                return "EPSG:4326"

    return "EPSG:4326"


def geometry_to_paths(geom):
    """
    把 LineString / MultiLineString / Polygon / MultiPolygon
    转成若干条点序列。
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


def read_tif_as_rgb(path):
    """
    用 rasterio 读取 tif，转成可视化 RGB uint8。
    兼容 uint8 / uint16 / float 数据。
    """
    with rasterio.open(path) as src:
        count = src.count

        if count >= 3:
            arr = src.read([1, 2, 3])
        elif count == 1:
            band = src.read(1)
            arr = np.stack([band, band, band], axis=0)
        else:
            raise ValueError(f"无法读取图像波段: {path}")

    arr = np.transpose(arr, (1, 2, 0)).astype(np.float32)

    # 如果已经是 0~255，直接裁剪
    if arr.max() <= 255 and arr.min() >= 0:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        return arr

    # 否则做百分位拉伸，便于显示
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


def transform_feature_geometry_to_dataset_crs(geom, src_crs, dst_crs):
    """
    将 geojson 几何从经纬度坐标转为 tif 的 CRS。
    """
    if geom is None:
        return None

    if dst_crs is None:
        return geom

    transformed = transform_geom(
        src_crs=src_crs,
        dst_crs=dst_crs,
        geom=geom,
        precision=6,
    )

    return transformed


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


def make_preview(post_path, geojson_path, save_path):
    """
    正确方式：
    geojson lon/lat -> dataset CRS -> pixel row/col -> draw
    """
    rgb = read_tif_as_rgb(post_path)
    pil_img = Image.fromarray(rgb).convert("RGB")
    draw = ImageDraw.Draw(pil_img)

    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    geojson_crs = get_geojson_crs(data)

    road_count = 0
    flooded_road_count = 0
    drawn_road_count = 0

    pixel_x_values = []
    pixel_y_values = []

    with rasterio.open(post_path) as src:
        dst_crs = src.crs

        for feat in data.get("features", []):
            props = feat.get("properties", {})

            if not is_road_feature(props):
                continue

            road_count += 1

            flooded = is_flooded_feature(props)

            if flooded:
                flooded_road_count += 1

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

            color = (255, 0, 0) if flooded else (255, 255, 255)
            width = 7 if flooded else 5

            for pix_path in pixel_paths:
                for x, y in pix_path:
                    pixel_x_values.append(x)
                    pixel_y_values.append(y)

                draw.line(pix_path, fill=color, width=width)

            drawn_road_count += 1

    pil_img.save(save_path)

    if pixel_x_values:
        pixel_range = {
            "x_min": float(np.min(pixel_x_values)),
            "x_max": float(np.max(pixel_x_values)),
            "y_min": float(np.min(pixel_y_values)),
            "y_max": float(np.max(pixel_y_values)),
        }
    else:
        pixel_range = None

    return {
        "road_count": road_count,
        "flooded_road_count": flooded_road_count,
        "drawn_road_count": drawn_road_count,
        "pixel_range": pixel_range,
    }


def get_basic_tif_info(path):
    with rasterio.open(path) as src:
        return {
            "width": src.width,
            "height": src.height,
            "count": src.count,
            "crs": str(src.crs),
            "transform": str(src.transform),
            "bounds": str(src.bounds),
        }


# ============================================================
# 3. 主流程
# ============================================================

def main():
    lines = []

    lines.append("=" * 100)
    lines.append("SpaceNet8 rasterio 几何对齐检查报告")
    lines.append("=" * 100)
    lines.append(f"SPACENET8_ROOT = {SPACENET8_ROOT}")
    lines.append(f"PREVIEW_DIR = {PREVIEW_DIR}")
    lines.append("")

    for dataset_name in DATASETS:
        dataset_root = SPACENET8_ROOT / dataset_name
        mapping_csv = find_mapping_csv(dataset_root)

        lines.append("=" * 100)
        lines.append(f"数据集: {dataset_name}")
        lines.append("=" * 100)
        lines.append(f"dataset_root = {dataset_root}")
        lines.append(f"mapping_csv = {mapping_csv}")

        if mapping_csv is None:
            lines.append("[错误] 找不到 mapping CSV")
            lines.append("")
            continue

        rows = read_mapping_rows(mapping_csv)
        lines.append(f"mapping 行数 = {len(rows)}")
        lines.append("")

        preview_count = 0

        # 优先找有 flooded road 的样本，这样能看到红线
        candidate_rows = []

        for row in rows:
            label_name = row.get("label", "").strip()

            if not label_name:
                continue

            label_path = find_file(dataset_root, "annotations", label_name)

            if label_path is None:
                continue

            try:
                with open(label_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                road_count = 0
                flooded_count = 0

                for feat in data.get("features", []):
                    props = feat.get("properties", {})

                    if is_road_feature(props):
                        road_count += 1

                        if is_flooded_feature(props):
                            flooded_count += 1

                candidate_rows.append((flooded_count, road_count, row))

            except Exception:
                continue

        # flooded 多的排前面
        candidate_rows = sorted(
            candidate_rows,
            key=lambda x: (x[0], x[1]),
            reverse=True,
        )

        for idx, (flooded_count, road_count, row) in enumerate(candidate_rows):
            if preview_count >= MAX_PREVIEW_PER_DATASET:
                break

            label_name = row.get("label", "").strip()
            pre_name = row.get("pre-event image", "").strip()
            post_name = row.get("post-event image 1", "").strip()

            if not label_name or not post_name:
                continue

            label_path = find_file(dataset_root, "annotations", label_name)
            post_path = find_file(dataset_root, "POST-event", post_name)

            if label_path is None or post_path is None:
                lines.append(f"[缺失] label 或 post: {label_name}, {post_name}")
                continue

            try:
                tif_info = get_basic_tif_info(post_path)

                save_name = f"{dataset_name}_{Path(label_name).stem}_road_preview_rasterio.png"
                save_path = PREVIEW_DIR / save_name

                preview_info = make_preview(
                    post_path=post_path,
                    geojson_path=label_path,
                    save_path=save_path,
                )

                lines.append(f"样本 {preview_count + 1}:")
                lines.append(f"  label = {label_name}")
                lines.append(f"  post  = {post_name}")
                lines.append(f"  tif_width_height = {tif_info['width']} x {tif_info['height']}")
                lines.append(f"  tif_crs = {tif_info['crs']}")
                lines.append(f"  tif_bounds = {tif_info['bounds']}")
                lines.append(f"  road_count = {preview_info['road_count']}")
                lines.append(f"  flooded_road_count = {preview_info['flooded_road_count']}")
                lines.append(f"  drawn_road_count = {preview_info['drawn_road_count']}")
                lines.append(f"  pixel_range_after_transform = {preview_info['pixel_range']}")
                lines.append(f"  preview = {save_path}")
                lines.append("")

                preview_count += 1

            except Exception as e:
                lines.append(f"[错误] {label_name}: {e}")
                lines.append("")

        lines.append(f"本数据集输出预览图数量: {preview_count}")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("=" * 100)
    print("rasterio 几何对齐检查完成")
    print(f"报告路径: {REPORT_PATH}")
    print(f"预览图目录: {PREVIEW_DIR}")
    print("=" * 100)

    print("\n".join(lines[:160]))


if __name__ == "__main__":
    main()
