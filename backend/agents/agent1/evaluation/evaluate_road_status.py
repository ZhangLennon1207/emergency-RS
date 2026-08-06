# -*- coding: utf-8 -*-
"""
27_eval_road_status_attresunet7ch_test.py

作用：
使用训练好的 road_status_attresunet7ch_best.pth
在 SpaceNet8 processed_road_status 的 test 集上做评估。

输出：
1. test 指标 JSON
2. test 预测 mask
3. test 彩色预测图
4. test 叠加图
5. test 对比图
"""

import os
import json
import csv
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import torch
from torch.utils.data import DataLoader

from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

PROJECT_ROOT = workspace_root()

TRAIN_SCRIPT_PATH = (
    PROJECT_ROOT
    / "agent1_visual_evidence"
    / "scripts"
    / "26_train_spacenet8_road_status_attresunet_7ch.py"
)

BEST_MODEL_PATH = (
    PROJECT_ROOT
    / "agent1_visual_evidence"
    / "checkpoints"
    / "road_status_attresunet7ch_best.pth"
)

OUTPUT_ROOT = (
    PROJECT_ROOT
    / "agent1_visual_evidence"
    / "outputs"
    / "road_status_attresunet7ch_test_eval"
)

OUTPUT_PRED_MASK = OUTPUT_ROOT / "pred_mask"
OUTPUT_PRED_COLOR = OUTPUT_ROOT / "pred_color"
OUTPUT_OVERLAY = OUTPUT_ROOT / "pred_overlay"
OUTPUT_COMPARE = OUTPUT_ROOT / "visual_compare"
OUTPUT_METRICS = OUTPUT_ROOT / "metrics"

for p in [
    OUTPUT_ROOT,
    OUTPUT_PRED_MASK,
    OUTPUT_PRED_COLOR,
    OUTPUT_OVERLAY,
    OUTPUT_COMPARE,
    OUTPUT_METRICS,
]:
    p.mkdir(parents=True, exist_ok=True)


BATCH_SIZE = 2
NUM_WORKERS = 0
MAX_VISUAL_SAVE = 80


# ============================================================
# 2. 加载训练脚本中的模型和工具函数
# ============================================================

def load_train_module():
    spec = importlib.util.spec_from_file_location(
        "road_status_train_module",
        str(TRAIN_SCRIPT_PATH),
    )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


# ============================================================
# 3. 可视化工具
# ============================================================

CLASS_COLORS = {
    0: (0, 0, 0),
    1: (255, 255, 255),
    2: (255, 0, 0),
}


def mask_to_color(mask):
    h, w = mask.shape
    color = np.zeros((h, w, 3), dtype=np.uint8)

    for cls_id, rgb in CLASS_COLORS.items():
        color[mask == cls_id] = rgb

    return color


def denorm_rgb(x):
    """
    x: [3,H,W]，范围 [-1,1]
    """
    arr = x.detach().cpu().numpy()
    arr = (arr * 0.5 + 0.5) * 255.0
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    arr = arr.transpose(1, 2, 0)
    return arr


def overlay_on_image(image_rgb, mask, alpha=0.75):
    color = mask_to_color(mask)
    overlay = image_rgb.copy()

    area = mask > 0

    overlay[area] = (
        image_rgb[area] * (1 - alpha)
        + color[area] * alpha
    ).astype(np.uint8)

    return overlay


def save_visual_compare(x, gt, pred, sample_id, save_path):
    """
    生成 3x2 对比图：
    Pre / Post / Road prior
    GT / Pred / Pred overlay
    """
    x = x.detach().cpu()

    pre_rgb = denorm_rgb(x[0:3])
    post_rgb = denorm_rgb(x[3:6])

    prior = x[6].numpy()
    prior_rgb = np.zeros_like(pre_rgb)
    prior_rgb[prior > 0.5] = (255, 255, 255)

    gt_color = mask_to_color(gt)
    pred_color = mask_to_color(pred)
    pred_overlay = overlay_on_image(post_rgb, pred)

    h, w = gt.shape

    canvas = Image.new("RGB", (w * 3, h * 2), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    items = [
        (pre_rgb, "Pre image"),
        (post_rgb, "Post image"),
        (prior_rgb, "Road prior"),
        (gt_color, "GT road status"),
        (pred_color, "Pred road status"),
        (pred_overlay, "Pred overlay"),
    ]

    for idx, (img, title) in enumerate(items):
        row = idx // 3
        col = idx % 3

        x0 = col * w
        y0 = row * h

        canvas.paste(Image.fromarray(img), (x0, y0))
        draw.text((x0 + 10, y0 + 10), title, fill=(255, 255, 255))

    draw.text((10, h * 2 - 28), sample_id, fill=(255, 255, 255))
    canvas.save(save_path)


# ============================================================
# 4. 单样本指标
# ============================================================

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
# 5. 主函数
# ============================================================

def main():
    print("=" * 100)
    print("道路状态模型 test 集评估")
    print("=" * 100)
    print(f"TRAIN_SCRIPT_PATH = {TRAIN_SCRIPT_PATH}")
    print(f"BEST_MODEL_PATH = {BEST_MODEL_PATH}")
    print(f"OUTPUT_ROOT = {OUTPUT_ROOT}")

    if not TRAIN_SCRIPT_PATH.exists():
        raise FileNotFoundError(f"找不到训练脚本: {TRAIN_SCRIPT_PATH}")

    if not BEST_MODEL_PATH.exists():
        raise FileNotFoundError(f"找不到最佳模型: {BEST_MODEL_PATH}")

    module = load_train_module()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("device =", device)

    ckpt = torch.load(BEST_MODEL_PATH, map_location=device)

    config = ckpt.get("config", {})

    base_channels = config.get("base_channels", module.BASE_CHANNELS)
    in_channels = config.get("in_channels", module.IN_CHANNELS)
    num_classes = config.get("num_classes", module.NUM_CLASSES)

    best_epoch = ckpt.get("epoch", None)
    best_score = ckpt.get("best_score", None)

    print(f"best epoch = {best_epoch}")
    print(f"best score = {best_score}")
    print(f"base_channels = {base_channels}")
    print(f"in_channels = {in_channels}")
    print(f"num_classes = {num_classes}")

    model = module.AttentionResUNet7ch(
        in_channels=in_channels,
        num_classes=num_classes,
        base_channels=base_channels,
    ).to(device)

    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    test_dataset = module.RoadStatusDataset("test", is_train=False)

    test_loader = DataLoader(
        test_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=True,
        drop_last=False,
    )

    print(f"test samples = {len(test_dataset)}")

    confmat = torch.zeros(
        module.NUM_CLASSES,
        module.NUM_CLASSES,
        dtype=torch.long,
        device=device,
    )

    sample_records = []
    visual_count = 0

    with torch.no_grad():
        for batch_idx, (x, y, sample_ids) in enumerate(test_loader):
            x = x.to(device)
            y = y.to(device)

            logits = model(x)
            pred = torch.argmax(logits, dim=1)

            confmat += module.fast_confusion_matrix(
                pred,
                y,
                module.NUM_CLASSES,
            ).to(device)

            for i in range(x.size(0)):
                sid = sample_ids[i]

                pred_np = pred[i].detach().cpu().numpy().astype(np.uint8)
                gt_np = y[i].detach().cpu().numpy().astype(np.uint8)

                pred_mask_path = OUTPUT_PRED_MASK / f"{sid}_pred_mask.png"
                pred_color_path = OUTPUT_PRED_COLOR / f"{sid}_pred_color.png"
                overlay_path = OUTPUT_OVERLAY / f"{sid}_pred_overlay.png"

                Image.fromarray(pred_np).save(pred_mask_path)

                pred_color = mask_to_color(pred_np)
                Image.fromarray(pred_color).save(pred_color_path)

                post_rgb = denorm_rgb(x[i].detach().cpu()[3:6])
                overlay = overlay_on_image(post_rgb, pred_np)
                Image.fromarray(overlay).save(overlay_path)

                compare_path = ""

                if visual_count < MAX_VISUAL_SAVE:
                    compare_path = OUTPUT_COMPARE / f"{sid}_compare.png"

                    save_visual_compare(
                        x=x[i],
                        gt=gt_np,
                        pred=pred_np,
                        sample_id=sid,
                        save_path=compare_path,
                    )

                    visual_count += 1

                sample_metric = compute_sample_metrics(pred_np, gt_np)

                record = {
                    "sample_id": sid,
                    "pred_mask_path": str(pred_mask_path),
                    "pred_color_path": str(pred_color_path),
                    "overlay_path": str(overlay_path),
                    "compare_path": str(compare_path),
                    **sample_metric,
                }

                sample_records.append(record)

            print(f"[{batch_idx + 1}/{len(test_loader)}] done")

    metrics = module.metrics_from_confmat(confmat.detach().cpu())

    summary = {
        "best_model_path": str(BEST_MODEL_PATH),
        "best_epoch": best_epoch,
        "best_score": best_score,
        "test_samples": len(test_dataset),
        "metrics": metrics,
        "confusion_matrix": confmat.detach().cpu().numpy().tolist(),
        "class_names": {
            0: "background",
            1: "road_intact",
            2: "road_flooded",
        },
    }

    summary_json = OUTPUT_METRICS / "test_metrics_summary.json"

    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    sample_csv = OUTPUT_METRICS / "test_sample_metrics.csv"

    fieldnames = [
        "sample_id",
        "road_intact_iou",
        "road_intact_dice",
        "road_intact_pred_pixels",
        "road_intact_gt_pixels",
        "road_flooded_iou",
        "road_flooded_dice",
        "road_flooded_pred_pixels",
        "road_flooded_gt_pixels",
        "pred_mask_path",
        "pred_color_path",
        "overlay_path",
        "compare_path",
    ]

    with open(sample_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in sample_records:
            writer.writerow(r)

    print("=" * 100)
    print("test 评估完成")
    print("=" * 100)
    print(f"summary_json = {summary_json}")
    print(f"sample_csv = {sample_csv}")
    print(f"pred_mask = {OUTPUT_PRED_MASK}")
    print(f"pred_color = {OUTPUT_PRED_COLOR}")
    print(f"overlay = {OUTPUT_OVERLAY}")
    print(f"visual_compare = {OUTPUT_COMPARE}")
    print("")
    print("核心指标：")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print("=" * 100)


if __name__ == "__main__":
    main()
