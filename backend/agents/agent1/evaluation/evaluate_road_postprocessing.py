# -*- coding: utf-8 -*-
"""
28_postprocess_road_status_test.py

作用：
对 27_eval_road_status_attresunet7ch_test.py 生成的道路状态预测结果做后处理。

输入：
agent1_visual_evidence/outputs/road_status_attresunet7ch_test_eval/pred_mask

参考：
data/SpaceNet8/processed_road_status/images_pre
data/SpaceNet8/processed_road_status/images_post
data/SpaceNet8/processed_road_status/masks_status

输出：
agent1_visual_evidence/outputs/road_status_attresunet7ch_test_eval_postprocess

后处理目标：
1. 删除小红点；
2. 填补红色道路中的小空洞；
3. 让红色道路更连续；
4. 红色只允许出现在 road prior 范围内；
5. 输出后处理前后指标对比。
"""

import csv
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

PROJECT_ROOT = workspace_root()

DATA_ROOT = PROJECT_ROOT / "data" / "SpaceNet8" / "processed_road_status"

PRE_DIR = DATA_ROOT / "images_pre"
POST_DIR = DATA_ROOT / "images_post"
GT_MASK_DIR = DATA_ROOT / "masks_status"

EVAL_ROOT = (
    PROJECT_ROOT
    / "agent1_visual_evidence"
    / "outputs"
    / "road_status_attresunet7ch_test_eval"
)

RAW_PRED_MASK_DIR = EVAL_ROOT / "pred_mask"

OUTPUT_ROOT = (
    PROJECT_ROOT
    / "agent1_visual_evidence"
    / "outputs"
    / "road_status_attresunet7ch_test_eval_postprocess"
)

OUTPUT_MASK_DIR = OUTPUT_ROOT / "post_mask"
OUTPUT_COLOR_DIR = OUTPUT_ROOT / "post_color"
OUTPUT_OVERLAY_DIR = OUTPUT_ROOT / "post_overlay"
OUTPUT_COMPARE_DIR = OUTPUT_ROOT / "visual_compare"
OUTPUT_METRICS_DIR = OUTPUT_ROOT / "metrics"

for p in [
    OUTPUT_ROOT,
    OUTPUT_MASK_DIR,
    OUTPUT_COLOR_DIR,
    OUTPUT_OVERLAY_DIR,
    OUTPUT_COMPARE_DIR,
    OUTPUT_METRICS_DIR,
]:
    p.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. 后处理参数
# ============================================================

"""
你后面主要调这几个参数：

MIN_RED_AREA：
- 越大，小红点删得越多；
- 如果删掉了真实小段受损道路，就调小。

CLOSE_KERNEL_SIZE：
- 越大，红色道路越容易连起来，空洞越少；
- 太大可能会把相近红色区域错误连起来。

DILATE_RED_ITER：
- 适当扩张红色区域，让红色更连续；
- 太大可能让红色变粗、范围变大。

SMALL_HOLE_CLOSE_KERNEL：
- 用来修补红色内部断裂。
"""

MIN_RED_AREA = 45

CLOSE_KERNEL_SIZE = 9
CLOSE_ITERATIONS = 1

DILATE_RED_ITER = 1

SMALL_HOLE_CLOSE_KERNEL = 7

# 是否用 road prior 重建白色道路
# True：最终道路区域来自 road prior，红色来自后处理结果；
# False：白色道路保留模型原始预测。
USE_ROAD_PRIOR_AS_FINAL_ROAD = True

# 最多保存多少张对比图
MAX_COMPARE_SAVE = 120


# ============================================================
# 3. 颜色
# ============================================================

CLASS_COLORS = {
    0: (0, 0, 0),          # 背景
    1: (255, 255, 255),    # 完好道路
    2: (255, 0, 0),        # 受影响道路
}

CLASS_NAMES = {
    0: "background",
    1: "road_intact",
    2: "road_flooded",
}


# ============================================================
# 4. 基础工具函数
# ============================================================

def load_mask(path):
    arr = np.array(Image.open(path).convert("L")).astype(np.uint8)
    arr[arr > 2] = 0
    return arr


def load_rgb(path):
    return np.array(Image.open(path).convert("RGB")).astype(np.uint8)


def save_mask(mask, path):
    Image.fromarray(mask.astype(np.uint8)).save(path)


def mask_to_color(mask):
    h, w = mask.shape
    color = np.zeros((h, w, 3), dtype=np.uint8)

    for cls_id, rgb in CLASS_COLORS.items():
        color[mask == cls_id] = rgb

    return color


def overlay_on_image(image_rgb, mask, alpha=0.75):
    color = mask_to_color(mask)
    overlay = image_rgb.copy()

    area = mask > 0

    overlay[area] = (
        image_rgb[area] * (1 - alpha)
        + color[area] * alpha
    ).astype(np.uint8)

    return overlay


def normalize_sample_id_from_pred_path(path):
    stem = path.stem

    suffix = "_pred_mask"

    if stem.endswith(suffix):
        return stem[: -len(suffix)]

    return stem


def list_pred_files():
    return sorted(RAW_PRED_MASK_DIR.glob("*_pred_mask.png"))


# ============================================================
# 5. 连通域和形态学后处理
# ============================================================

def remove_small_components(binary, min_area):
    """
    删除小连通域。
    binary: 0/1
    """
    binary = (binary > 0).astype(np.uint8)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary,
        connectivity=8,
    )

    out = np.zeros_like(binary, dtype=np.uint8)

    for label_id in range(1, num_labels):
        area = stats[label_id, cv2.CC_STAT_AREA]

        if area >= min_area:
            out[labels == label_id] = 1

    return out


def morph_close(binary, kernel_size, iterations=1):
    binary = (binary > 0).astype(np.uint8)

    if kernel_size <= 1:
        return binary

    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (kernel_size, kernel_size),
    )

    out = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=iterations,
    )

    return (out > 0).astype(np.uint8)


def morph_dilate(binary, kernel_size=3, iterations=1):
    binary = (binary > 0).astype(np.uint8)

    if iterations <= 0:
        return binary

    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (kernel_size, kernel_size),
    )

    out = cv2.dilate(binary, kernel, iterations=iterations)

    return (out > 0).astype(np.uint8)


def postprocess_red_mask(raw_pred_mask, road_prior):
    """
    对红色道路 class=2 做后处理。

    输入：
    raw_pred_mask:
      0/1/2 模型原始预测
    road_prior:
      0/1 道路先验区域

    输出：
    post_red:
      0/1 后处理后的红色区域
    """
    road_prior = (road_prior > 0).astype(np.uint8)

    red = (raw_pred_mask == 2).astype(np.uint8)

    # 1. 红色只允许在 road prior 内
    red = red * road_prior

    # 2. 先删除非常小的红点
    red = remove_small_components(red, min_area=max(8, MIN_RED_AREA // 3))

    # 3. 闭运算，让红色道路更连续，填补小空洞
    red = morph_close(
        red,
        kernel_size=CLOSE_KERNEL_SIZE,
        iterations=CLOSE_ITERATIONS,
    )

    # 4. 再次限制在 road prior 内
    red = red * road_prior

    # 5. 可选轻微膨胀
    red = morph_dilate(
        red,
        kernel_size=3,
        iterations=DILATE_RED_ITER,
    )

    red = red * road_prior

    # 6. 再做一次小闭运算，补小缺口
    red = morph_close(
        red,
        kernel_size=SMALL_HOLE_CLOSE_KERNEL,
        iterations=1,
    )

    red = red * road_prior

    # 7. 删除最终小连通域
    red = remove_small_components(
        red,
        min_area=MIN_RED_AREA,
    )

    red = red * road_prior

    return red.astype(np.uint8)


def make_post_mask(raw_pred_mask, gt_mask):
    """
    当前测试集后处理使用 gt_mask > 0 作为 road prior。

    这与训练/测试时模型输入一致：
    road prior = mask > 0

    后续接入 EBD 时：
    road prior 会换成 road_unet 的道路分割结果。
    """
    road_prior = (gt_mask > 0).astype(np.uint8)

    post_red = postprocess_red_mask(
        raw_pred_mask=raw_pred_mask,
        road_prior=road_prior,
    )

    post_mask = np.zeros_like(raw_pred_mask, dtype=np.uint8)

    if USE_ROAD_PRIOR_AS_FINAL_ROAD:
        # 最终白色道路来自 road prior
        post_mask[road_prior > 0] = 1
    else:
        # 白色道路保留模型预测
        post_mask[raw_pred_mask == 1] = 1

    # 红色覆盖白色
    post_mask[post_red > 0] = 2

    return post_mask


# ============================================================
# 6. 指标计算
# ============================================================

def compute_confusion_matrix(pred, gt, num_classes=3):
    pred = pred.reshape(-1)
    gt = gt.reshape(-1)

    valid = (gt >= 0) & (gt < num_classes)

    hist = np.bincount(
        num_classes * gt[valid] + pred[valid],
        minlength=num_classes ** 2,
    ).reshape(num_classes, num_classes)

    return hist


def metrics_from_confmat(confmat):
    confmat = confmat.astype(np.float64)

    metrics = {}

    ious = []
    dices = []

    for cls in range(3):
        tp = confmat[cls, cls]
        fp = confmat[:, cls].sum() - tp
        fn = confmat[cls, :].sum() - tp

        iou = tp / (tp + fp + fn + 1e-6)
        dice = (2 * tp) / (2 * tp + fp + fn + 1e-6)

        metrics[f"iou_{cls}"] = float(iou)
        metrics[f"dice_{cls}"] = float(dice)

        ious.append(iou)
        dices.append(dice)

    metrics["miou_road"] = float((ious[1] + ious[2]) / 2)
    metrics["mdice_road"] = float((dices[1] + dices[2]) / 2)

    cls = 2

    tp = confmat[cls, cls]
    fp = confmat[:, cls].sum() - tp
    fn = confmat[cls, :].sum() - tp

    precision = tp / (tp + fp + 1e-6)
    recall = tp / (tp + fn + 1e-6)

    metrics["flooded_precision"] = float(precision)
    metrics["flooded_recall"] = float(recall)

    return metrics


def compute_sample_metrics(pred, gt):
    result = {}

    for cls_id, name in [
        (1, "road_intact"),
        (2, "road_flooded"),
    ]:
        pred_area = pred == cls_id
        gt_area = gt == cls_id

        inter = np.logical_and(pred_area, gt_area).sum()
        union = np.logical_or(pred_area, gt_area).sum()

        pred_sum = pred_area.sum()
        gt_sum = gt_area.sum()

        if union > 0:
            iou = inter / union
        else:
            iou = None

        if pred_sum + gt_sum > 0:
            dice = 2 * inter / (pred_sum + gt_sum)
        else:
            dice = None

        result[f"{name}_iou"] = iou
        result[f"{name}_dice"] = dice
        result[f"{name}_pred_pixels"] = int(pred_sum)
        result[f"{name}_gt_pixels"] = int(gt_sum)

    return result


# ============================================================
# 7. 可视化
# ============================================================

def make_compare_image(
    pre_rgb,
    post_rgb,
    gt_mask,
    raw_pred_mask,
    post_mask,
    save_path,
    sample_id,
):
    """
    生成 3x2 对比图：
    Pre / Post / GT
    Raw Pred / Postprocessed / Overlay
    """
    h, w = gt_mask.shape

    gt_color = mask_to_color(gt_mask)
    raw_color = mask_to_color(raw_pred_mask)
    post_color = mask_to_color(post_mask)
    post_overlay = overlay_on_image(post_rgb, post_mask)

    canvas = Image.new("RGB", (w * 3, h * 2), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    items = [
        (pre_rgb, "Pre image"),
        (post_rgb, "Post image"),
        (gt_color, "GT road status"),
        (raw_color, "Raw prediction"),
        (post_color, "Postprocessed"),
        (post_overlay, "Post overlay"),
    ]

    for idx, (img, title) in enumerate(items):
        row = idx // 3
        col = idx % 3

        x0 = col * w
        y0 = row * h

        canvas.paste(Image.fromarray(img), (x0, y0))
        draw.text((x0 + 10, y0 + 10), title, fill=(255, 255, 255))

    draw.text((10, h * 2 - 30), sample_id, fill=(255, 255, 255))

    canvas.save(save_path)


# ============================================================
# 8. 主函数
# ============================================================

def main():
    print("=" * 100)
    print("道路状态预测后处理")
    print("=" * 100)
    print(f"RAW_PRED_MASK_DIR = {RAW_PRED_MASK_DIR}")
    print(f"OUTPUT_ROOT = {OUTPUT_ROOT}")
    print(f"MIN_RED_AREA = {MIN_RED_AREA}")
    print(f"CLOSE_KERNEL_SIZE = {CLOSE_KERNEL_SIZE}")
    print(f"DILATE_RED_ITER = {DILATE_RED_ITER}")
    print(f"USE_ROAD_PRIOR_AS_FINAL_ROAD = {USE_ROAD_PRIOR_AS_FINAL_ROAD}")
    print("=" * 100)

    if not RAW_PRED_MASK_DIR.exists():
        raise FileNotFoundError(f"找不到原始预测目录: {RAW_PRED_MASK_DIR}")

    pred_files = list_pred_files()

    print(f"待后处理预测 mask 数量: {len(pred_files)}")

    if len(pred_files) == 0:
        print("没有找到 *_pred_mask.png")
        return

    raw_confmat = np.zeros((3, 3), dtype=np.int64)
    post_confmat = np.zeros((3, 3), dtype=np.int64)

    sample_records = []

    visual_count = 0

    for idx, pred_path in enumerate(pred_files, start=1):
        sample_id = normalize_sample_id_from_pred_path(pred_path)

        pre_path = PRE_DIR / f"{sample_id}_pre.png"
        post_path = POST_DIR / f"{sample_id}_post.png"
        gt_path = GT_MASK_DIR / f"{sample_id}_road_status_mask.png"

        if not gt_path.exists():
            print(f"[跳过] 找不到 GT: {sample_id}")
            continue

        raw_pred = load_mask(pred_path)
        gt = load_mask(gt_path)

        post_mask = make_post_mask(
            raw_pred_mask=raw_pred,
            gt_mask=gt,
        )

        raw_confmat += compute_confusion_matrix(raw_pred, gt)
        post_confmat += compute_confusion_matrix(post_mask, gt)

        post_mask_path = OUTPUT_MASK_DIR / f"{sample_id}_post_mask.png"
        post_color_path = OUTPUT_COLOR_DIR / f"{sample_id}_post_color.png"
        post_overlay_path = OUTPUT_OVERLAY_DIR / f"{sample_id}_post_overlay.png"

        save_mask(post_mask, post_mask_path)
        Image.fromarray(mask_to_color(post_mask)).save(post_color_path)

        post_rgb = load_rgb(post_path)
        pre_rgb = load_rgb(pre_path)

        overlay = overlay_on_image(post_rgb, post_mask)
        Image.fromarray(overlay).save(post_overlay_path)

        compare_path = ""

        if visual_count < MAX_COMPARE_SAVE:
            compare_path = OUTPUT_COMPARE_DIR / f"{sample_id}_compare.png"

            make_compare_image(
                pre_rgb=pre_rgb,
                post_rgb=post_rgb,
                gt_mask=gt,
                raw_pred_mask=raw_pred,
                post_mask=post_mask,
                save_path=compare_path,
                sample_id=sample_id,
            )

            visual_count += 1

        raw_sample_metric = compute_sample_metrics(raw_pred, gt)
        post_sample_metric = compute_sample_metrics(post_mask, gt)

        record = {
            "sample_id": sample_id,
            "raw_road_intact_iou": raw_sample_metric["road_intact_iou"],
            "raw_road_flooded_iou": raw_sample_metric["road_flooded_iou"],
            "post_road_intact_iou": post_sample_metric["road_intact_iou"],
            "post_road_flooded_iou": post_sample_metric["road_flooded_iou"],
            "raw_flooded_pred_pixels": raw_sample_metric["road_flooded_pred_pixels"],
            "post_flooded_pred_pixels": post_sample_metric["road_flooded_pred_pixels"],
            "gt_flooded_pixels": post_sample_metric["road_flooded_gt_pixels"],
            "post_mask_path": str(post_mask_path),
            "post_color_path": str(post_color_path),
            "post_overlay_path": str(post_overlay_path),
            "compare_path": str(compare_path),
        }

        sample_records.append(record)

        print(
            f"[{idx}/{len(pred_files)}] {sample_id} | "
            f"raw_red={record['raw_flooded_pred_pixels']}, "
            f"post_red={record['post_flooded_pred_pixels']}, "
            f"gt_red={record['gt_flooded_pixels']}"
        )

    raw_metrics = metrics_from_confmat(raw_confmat)
    post_metrics = metrics_from_confmat(post_confmat)

    summary = {
        "raw_pred_mask_dir": str(RAW_PRED_MASK_DIR),
        "output_root": str(OUTPUT_ROOT),
        "params": {
            "min_red_area": MIN_RED_AREA,
            "close_kernel_size": CLOSE_KERNEL_SIZE,
            "close_iterations": CLOSE_ITERATIONS,
            "dilate_red_iter": DILATE_RED_ITER,
            "small_hole_close_kernel": SMALL_HOLE_CLOSE_KERNEL,
            "use_road_prior_as_final_road": USE_ROAD_PRIOR_AS_FINAL_ROAD,
        },
        "num_samples": len(sample_records),
        "raw_metrics": raw_metrics,
        "post_metrics": post_metrics,
        "raw_confusion_matrix": raw_confmat.tolist(),
        "post_confusion_matrix": post_confmat.tolist(),
    }

    summary_path = OUTPUT_METRICS_DIR / "postprocess_metrics_summary.json"

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    sample_csv_path = OUTPUT_METRICS_DIR / "postprocess_sample_metrics.csv"

    fieldnames = [
        "sample_id",
        "raw_road_intact_iou",
        "raw_road_flooded_iou",
        "post_road_intact_iou",
        "post_road_flooded_iou",
        "raw_flooded_pred_pixels",
        "post_flooded_pred_pixels",
        "gt_flooded_pixels",
        "post_mask_path",
        "post_color_path",
        "post_overlay_path",
        "compare_path",
    ]

    with open(sample_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in sample_records:
            writer.writerow(r)

    print("=" * 100)
    print("后处理完成")
    print("=" * 100)
    print(f"post mask: {OUTPUT_MASK_DIR}")
    print(f"post color: {OUTPUT_COLOR_DIR}")
    print(f"post overlay: {OUTPUT_OVERLAY_DIR}")
    print(f"compare: {OUTPUT_COMPARE_DIR}")
    print(f"summary: {summary_path}")
    print(f"sample csv: {sample_csv_path}")
    print("")
    print("原始预测指标：")
    print(json.dumps(raw_metrics, ensure_ascii=False, indent=2))
    print("")
    print("后处理后指标：")
    print(json.dumps(post_metrics, ensure_ascii=False, indent=2))
    print("=" * 100)


if __name__ == "__main__":
    main()
