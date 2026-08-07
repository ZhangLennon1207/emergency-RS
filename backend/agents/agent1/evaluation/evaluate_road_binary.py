# -*- coding: utf-8 -*-
"""
15_predict_road_unet_test10_postprocess.py

作用：
1. 加载 road_unet_best.pth；
2. 从 test.csv 中取 10 张道路样本；
3. 生成 raw 道路预测；
4. 对 raw 道路预测进行 clean 后处理；
5. 再生成 smooth_display 展示版道路结果；
6. 输出 raw / clean / smooth_display 三套结果。

输出：
- raw_mask_gray
- clean_mask_gray
- smooth_display_mask_gray
- raw_overlay
- clean_overlay
- smooth_display_overlay
- visual_compare_raw_clean_smooth
"""

import csv
from pathlib import Path
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

import torch
import torch.nn as nn

import matplotlib.pyplot as plt

from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径和参数
# ============================================================

PROJECT_ROOT = workspace_root()

TEST_CSV = PROJECT_ROOT / "data" / "openearthmap" / "processed" / "splits" / "test.csv"

CHECKPOINT_PATH = (
    PROJECT_ROOT
    / "agent1_visual_evidence"
    / "checkpoints"
    / "road_unet_best.pth"
)

OUTPUT_ROOT = (
    PROJECT_ROOT
    / "agent1_visual_evidence"
    / "outputs"
    / "road_pred_test10_postprocess"
)

OUTPUT_COMPARE = OUTPUT_ROOT / "visual_compare_raw_clean_smooth"

OUTPUT_RAW_MASK = OUTPUT_ROOT / "raw_mask_gray"
OUTPUT_CLEAN_MASK = OUTPUT_ROOT / "clean_mask_gray"
OUTPUT_SMOOTH_MASK = OUTPUT_ROOT / "smooth_display_mask_gray"

OUTPUT_RAW_OVERLAY = OUTPUT_ROOT / "raw_overlay"
OUTPUT_CLEAN_OVERLAY = OUTPUT_ROOT / "clean_overlay"
OUTPUT_SMOOTH_OVERLAY = OUTPUT_ROOT / "smooth_display_overlay"

for p in [
    OUTPUT_ROOT,
    OUTPUT_COMPARE,
    OUTPUT_RAW_MASK,
    OUTPUT_CLEAN_MASK,
    OUTPUT_SMOOTH_MASK,
    OUTPUT_RAW_OVERLAY,
    OUTPUT_CLEAN_OVERLAY,
    OUTPUT_SMOOTH_OVERLAY,
]:
    p.mkdir(parents=True, exist_ok=True)


NUM_SAMPLES = 10

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# 2. 预测与 clean 后处理参数
# ============================================================

# 原始预测阈值
# 0.55 比 0.5 更保守，可以减少停车场、广场、空地误检
THRESHOLD = 0.55

# 删除小白点、小碎片
# 如果小白点仍然多，可以改成 100 或 120
# 如果乡村细路被删太多，可以改成 50
MIN_AREA = 80

# clean 版闭运算核大小
# 用来连接道路轻微断裂、平滑边界
CLOSE_KERNEL = 5

# clean 版是否开运算
# 开运算会去毛刺，但可能切断细路，所以默认 False
USE_OPENING = False
OPEN_KERNEL = 3


# ============================================================
# 3. smooth_display 展示版参数
# ============================================================

# 展示版只用于可视化/PPT，不建议直接用于严肃统计
USE_SMOOTH_DISPLAY = True

# 展示版闭运算更强一点，让道路内部更连续
DISPLAY_CLOSE_KERNEL = 7

# 展示版中值滤波，减少边缘毛刺
DISPLAY_MEDIAN_KERNEL = 3

# 是否填补道路内部小黑洞
FILL_SMALL_HOLES = True

# 最大填洞面积
# 如果道路内部黑洞还多，可以改大到 800 或 1000
# 如果道路被填得太粗，可以改小到 300
MAX_HOLE_AREA = 500

# 展示版最终再删一次小碎片
DISPLAY_MIN_AREA = 100


# ============================================================
# 4. 模型结构：必须和训练脚本一致
# ============================================================

class DoubleConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()

        self.net = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),

            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.net(x)


class RoadUNet(nn.Module):
    def __init__(self, in_channels=3, out_channels=1, base_channels=32):
        super().__init__()

        self.enc1 = DoubleConv(in_channels, base_channels)
        self.pool1 = nn.MaxPool2d(2)

        self.enc2 = DoubleConv(base_channels, base_channels * 2)
        self.pool2 = nn.MaxPool2d(2)

        self.enc3 = DoubleConv(base_channels * 2, base_channels * 4)
        self.pool3 = nn.MaxPool2d(2)

        self.enc4 = DoubleConv(base_channels * 4, base_channels * 8)
        self.pool4 = nn.MaxPool2d(2)

        self.bottleneck = DoubleConv(base_channels * 8, base_channels * 16)

        self.up4 = nn.ConvTranspose2d(
            base_channels * 16,
            base_channels * 8,
            kernel_size=2,
            stride=2,
        )
        self.dec4 = DoubleConv(base_channels * 16, base_channels * 8)

        self.up3 = nn.ConvTranspose2d(
            base_channels * 8,
            base_channels * 4,
            kernel_size=2,
            stride=2,
        )
        self.dec3 = DoubleConv(base_channels * 8, base_channels * 4)

        self.up2 = nn.ConvTranspose2d(
            base_channels * 4,
            base_channels * 2,
            kernel_size=2,
            stride=2,
        )
        self.dec2 = DoubleConv(base_channels * 4, base_channels * 2)

        self.up1 = nn.ConvTranspose2d(
            base_channels * 2,
            base_channels,
            kernel_size=2,
            stride=2,
        )
        self.dec1 = DoubleConv(base_channels * 2, base_channels)

        self.out_conv = nn.Conv2d(base_channels, out_channels, kernel_size=1)

    def forward(self, x):
        e1 = self.enc1(x)

        e2 = self.enc2(self.pool1(e1))

        e3 = self.enc3(self.pool2(e2))

        e4 = self.enc4(self.pool3(e3))

        b = self.bottleneck(self.pool4(e4))

        d4 = self.up4(b)
        d4 = torch.cat([d4, e4], dim=1)
        d4 = self.dec4(d4)

        d3 = self.up3(d4)
        d3 = torch.cat([d3, e3], dim=1)
        d3 = self.dec3(d3)

        d2 = self.up2(d3)
        d2 = torch.cat([d2, e2], dim=1)
        d2 = self.dec2(d2)

        d1 = self.up1(d2)
        d1 = torch.cat([d1, e1], dim=1)
        d1 = self.dec1(d1)

        logits = self.out_conv(d1)
        return logits


# ============================================================
# 5. 基础工具函数
# ============================================================

def read_csv_records(csv_path):
    records = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    return records


def get_sample_id(row):
    region = row["region"]
    stem = row["stem"]

    # 避免 accra_accra_39 这种重复命名
    if stem.startswith(region + "_"):
        return stem

    return f"{region}_{stem}"


def load_model(checkpoint_path):
    try:
        checkpoint = torch.load(checkpoint_path, map_location=DEVICE, weights_only=False)
    except TypeError:
        checkpoint = torch.load(checkpoint_path, map_location=DEVICE)

    if isinstance(checkpoint, dict):
        img_size = checkpoint.get("img_size", 768)
        base_channels = checkpoint.get("base_channels", 32)
    else:
        img_size = 768
        base_channels = 32

    model = RoadUNet(
        in_channels=3,
        out_channels=1,
        base_channels=base_channels,
    ).to(DEVICE)

    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        model.load_state_dict(checkpoint["model_state_dict"])
    else:
        model.load_state_dict(checkpoint)

    model.eval()

    print("模型加载成功")
    print(f"checkpoint = {checkpoint_path}")
    print(f"img_size = {img_size}")
    print(f"base_channels = {base_channels}")

    if isinstance(checkpoint, dict):
        if "epoch" in checkpoint:
            print(f"checkpoint epoch = {checkpoint['epoch']}")
        if "best_val_iou" in checkpoint:
            print(f"best_val_iou = {checkpoint['best_val_iou']}")

    return model, img_size


def save_gray_mask(mask, save_path):
    Image.fromarray((mask * 255).astype(np.uint8)).save(save_path)


def save_color_image(img_np, save_path):
    Image.fromarray(img_np.astype(np.uint8)).save(save_path)


def mask_to_color(mask):
    """
    0 背景 = 黑色
    1 道路 = 白色
    """
    h, w = mask.shape
    color = np.zeros((h, w, 3), dtype=np.uint8)
    color[mask == 1] = (255, 255, 255)
    return color


def overlay_road_on_image(image_rgb, road_mask, alpha=0.55):
    """
    只把道路区域叠加为白色，背景保持原图。
    """
    overlay = image_rgb.copy()

    road_area = road_mask == 1

    road_color = np.zeros_like(image_rgb, dtype=np.uint8)
    road_color[road_area] = (255, 255, 255)

    overlay[road_area] = (
        image_rgb[road_area] * (1 - alpha)
        + road_color[road_area] * alpha
    ).astype(np.uint8)

    return overlay


# ============================================================
# 6. 二值形态学与连通域函数
# ============================================================

def binary_morphology(mask, mode="close", kernel_size=5):
    """
    使用 PIL 做二值形态学操作。
    mask: 0/1 numpy array

    mode:
    - close: 膨胀后腐蚀，用于连接断裂、填小缝
    - open:  腐蚀后膨胀，用于去毛刺、小噪声
    """
    if kernel_size < 3:
        return mask.astype(np.uint8)

    if kernel_size % 2 == 0:
        kernel_size += 1

    mask_img = Image.fromarray((mask * 255).astype(np.uint8))

    if mode == "close":
        mask_img = mask_img.filter(ImageFilter.MaxFilter(kernel_size))
        mask_img = mask_img.filter(ImageFilter.MinFilter(kernel_size))

    elif mode == "open":
        mask_img = mask_img.filter(ImageFilter.MinFilter(kernel_size))
        mask_img = mask_img.filter(ImageFilter.MaxFilter(kernel_size))

    else:
        raise ValueError(f"未知 mode: {mode}")

    out = np.array(mask_img)
    out = (out > 127).astype(np.uint8)

    return out


def remove_small_components(mask, min_area=80):
    """
    删除小连通域。
    不依赖 opencv/scipy，直接 BFS。
    """
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    output = np.zeros((h, w), dtype=np.uint8)

    directions = [
        (-1, 0), (1, 0), (0, -1), (0, 1),
        (-1, -1), (-1, 1), (1, -1), (1, 1),
    ]

    for y in range(h):
        for x in range(w):
            if mask[y, x] == 0 or visited[y, x]:
                continue

            queue = deque()
            queue.append((y, x))
            visited[y, x] = True

            component_pixels = []

            while queue:
                cy, cx = queue.popleft()
                component_pixels.append((cy, cx))

                for dy, dx in directions:
                    ny, nx = cy + dy, cx + dx

                    if ny < 0 or ny >= h or nx < 0 or nx >= w:
                        continue

                    if visited[ny, nx]:
                        continue

                    if mask[ny, nx] == 0:
                        continue

                    visited[ny, nx] = True
                    queue.append((ny, nx))

            area = len(component_pixels)

            if area >= min_area:
                for py, px in component_pixels:
                    output[py, px] = 1

    return output


def fill_small_holes(mask, max_hole_area=500):
    """
    填补二值 mask 内部的小黑洞。
    只填补没有接触图像边界的背景连通域。
    """
    h, w = mask.shape

    visited = np.zeros((h, w), dtype=bool)
    output = mask.copy().astype(np.uint8)

    directions = [
        (-1, 0), (1, 0), (0, -1), (0, 1),
        (-1, -1), (-1, 1), (1, -1), (1, 1),
    ]

    for y in range(h):
        for x in range(w):
            if output[y, x] != 0 or visited[y, x]:
                continue

            queue = deque()
            queue.append((y, x))
            visited[y, x] = True

            component_pixels = []
            touches_border = False

            while queue:
                cy, cx = queue.popleft()
                component_pixels.append((cy, cx))

                if cy == 0 or cy == h - 1 or cx == 0 or cx == w - 1:
                    touches_border = True

                for dy, dx in directions:
                    ny, nx = cy + dy, cx + dx

                    if ny < 0 or ny >= h or nx < 0 or nx >= w:
                        continue

                    if visited[ny, nx]:
                        continue

                    if output[ny, nx] != 0:
                        continue

                    visited[ny, nx] = True
                    queue.append((ny, nx))

            area = len(component_pixels)

            if not touches_border and area <= max_hole_area:
                for py, px in component_pixels:
                    output[py, px] = 1

    return output


# ============================================================
# 7. 道路后处理
# ============================================================

def postprocess_road_mask(raw_mask):
    """
    clean 版道路后处理：
    1. 删除小连通域；
    2. 闭运算连接轻微断裂；
    3. 可选开运算去毛刺；
    4. 再次删除小碎片。

    clean_mask 可以作为后续融合和统计的主要道路 mask。
    """
    clean = raw_mask.copy().astype(np.uint8)

    clean = remove_small_components(clean, min_area=MIN_AREA)

    if CLOSE_KERNEL and CLOSE_KERNEL >= 3:
        clean = binary_morphology(
            clean,
            mode="close",
            kernel_size=CLOSE_KERNEL,
        )

    if USE_OPENING and OPEN_KERNEL and OPEN_KERNEL >= 3:
        clean = binary_morphology(
            clean,
            mode="open",
            kernel_size=OPEN_KERNEL,
        )

    clean = remove_small_components(clean, min_area=MIN_AREA)

    return clean


def smooth_road_mask_for_display(clean_mask):
    """
    展示版道路平滑：
    1. 更强闭运算，连接道路内部裂缝；
    2. 填小孔洞；
    3. 中值滤波平滑边缘；
    4. 删除小碎片。

    注意：
    smooth_display_mask 主要用于可视化展示，不建议直接替代 clean_mask 做严肃统计。
    """
    display = clean_mask.copy().astype(np.uint8)

    if DISPLAY_CLOSE_KERNEL and DISPLAY_CLOSE_KERNEL >= 3:
        display = binary_morphology(
            display,
            mode="close",
            kernel_size=DISPLAY_CLOSE_KERNEL,
        )

    if FILL_SMALL_HOLES:
        display = fill_small_holes(
            display,
            max_hole_area=MAX_HOLE_AREA,
        )

    if DISPLAY_MEDIAN_KERNEL and DISPLAY_MEDIAN_KERNEL >= 3:
        k = DISPLAY_MEDIAN_KERNEL
        if k % 2 == 0:
            k += 1

        img = Image.fromarray((display * 255).astype(np.uint8))
        img = img.filter(ImageFilter.MedianFilter(k))
        display = np.array(img)
        display = (display > 127).astype(np.uint8)

    display = remove_small_components(
        display,
        min_area=DISPLAY_MIN_AREA,
    )

    return display


# ============================================================
# 8. 单张预测
# ============================================================

def predict_one(model, image_path, mask_path, img_size):
    image = Image.open(image_path).convert("RGB")
    gt_mask = Image.open(mask_path).convert("L")

    image = image.resize((img_size, img_size), Image.BILINEAR)
    gt_mask = gt_mask.resize((img_size, img_size), Image.NEAREST)

    image_np = np.array(image).astype(np.float32) / 255.0

    gt_mask_np = np.array(gt_mask).astype(np.uint8)
    gt_mask_np = (gt_mask_np > 0).astype(np.uint8)

    image_tensor = torch.from_numpy(
        np.transpose(image_np, (2, 0, 1))
    ).float().unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        logits = model(image_tensor)
        prob = torch.sigmoid(logits)
        raw_pred = (prob >= THRESHOLD).float()

    raw_mask = raw_pred.squeeze().cpu().numpy().astype(np.uint8)

    clean_mask = postprocess_road_mask(raw_mask)

    if USE_SMOOTH_DISPLAY:
        smooth_mask = smooth_road_mask_for_display(clean_mask)
    else:
        smooth_mask = clean_mask.copy()

    image_rgb = (image_np * 255.0).clip(0, 255).astype(np.uint8)

    return image_rgb, gt_mask_np, raw_mask, clean_mask, smooth_mask


# ============================================================
# 9. 绘制对比图
# ============================================================

def draw_compare_figure(
    image_rgb,
    gt_mask,
    raw_mask,
    clean_mask,
    smooth_mask,
    raw_overlay,
    clean_overlay,
    smooth_overlay,
    save_path,
    sample_id,
):
    gt_color = mask_to_color(gt_mask)
    raw_color = mask_to_color(raw_mask)
    clean_color = mask_to_color(clean_mask)
    smooth_color = mask_to_color(smooth_mask)

    plt.figure(figsize=(22, 12))

    plt.subplot(2, 4, 1)
    plt.imshow(image_rgb)
    plt.title("Original image")
    plt.axis("off")

    plt.subplot(2, 4, 2)
    plt.imshow(gt_color)
    plt.title("GT road mask")
    plt.axis("off")

    plt.subplot(2, 4, 3)
    plt.imshow(raw_color)
    plt.title(f"Raw pred\nthreshold={THRESHOLD}")
    plt.axis("off")

    plt.subplot(2, 4, 4)
    plt.imshow(clean_color)
    plt.title(f"Clean pred\nMIN_AREA={MIN_AREA}, CLOSE={CLOSE_KERNEL}")
    plt.axis("off")

    plt.subplot(2, 4, 5)
    plt.imshow(smooth_color)
    plt.title(
        f"Smooth display\nCLOSE={DISPLAY_CLOSE_KERNEL}, MEDIAN={DISPLAY_MEDIAN_KERNEL}"
    )
    plt.axis("off")

    plt.subplot(2, 4, 6)
    plt.imshow(raw_overlay)
    plt.title("Raw overlay")
    plt.axis("off")

    plt.subplot(2, 4, 7)
    plt.imshow(clean_overlay)
    plt.title("Clean overlay")
    plt.axis("off")

    plt.subplot(2, 4, 8)
    plt.imshow(smooth_overlay)
    plt.title("Smooth display overlay")
    plt.axis("off")

    plt.suptitle(sample_id, fontsize=16)
    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()


# ============================================================
# 10. 主函数
# ============================================================

def main():
    print("=" * 80)
    print("道路预测 + clean 后处理 + smooth 展示版")
    print("=" * 80)
    print(f"TEST_CSV = {TEST_CSV}")
    print(f"CHECKPOINT_PATH = {CHECKPOINT_PATH}")
    print(f"OUTPUT_ROOT = {OUTPUT_ROOT}")
    print(f"DEVICE = {DEVICE}")
    print("-" * 80)
    print(f"THRESHOLD = {THRESHOLD}")
    print(f"MIN_AREA = {MIN_AREA}")
    print(f"CLOSE_KERNEL = {CLOSE_KERNEL}")
    print(f"USE_OPENING = {USE_OPENING}")
    print(f"OPEN_KERNEL = {OPEN_KERNEL}")
    print("-" * 80)
    print(f"USE_SMOOTH_DISPLAY = {USE_SMOOTH_DISPLAY}")
    print(f"DISPLAY_CLOSE_KERNEL = {DISPLAY_CLOSE_KERNEL}")
    print(f"DISPLAY_MEDIAN_KERNEL = {DISPLAY_MEDIAN_KERNEL}")
    print(f"FILL_SMALL_HOLES = {FILL_SMALL_HOLES}")
    print(f"MAX_HOLE_AREA = {MAX_HOLE_AREA}")
    print(f"DISPLAY_MIN_AREA = {DISPLAY_MIN_AREA}")
    print("=" * 80)

    if not TEST_CSV.exists():
        raise FileNotFoundError(f"找不到 TEST_CSV: {TEST_CSV}")

    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(f"找不到 CHECKPOINT_PATH: {CHECKPOINT_PATH}")

    records = read_csv_records(TEST_CSV)

    print(f"test.csv 样本数: {len(records)}")

    if len(records) == 0:
        raise ValueError("test.csv 为空")

    selected_records = records[:min(NUM_SAMPLES, len(records))]

    model, img_size = load_model(CHECKPOINT_PATH)

    result_txt = OUTPUT_ROOT / "postprocess_result.txt"

    with open(result_txt, "w", encoding="utf-8-sig") as fw:
        fw.write("道路预测后处理结果\n")
        fw.write("=" * 80 + "\n")
        fw.write(f"checkpoint = {CHECKPOINT_PATH}\n")
        fw.write(f"threshold = {THRESHOLD}\n")
        fw.write(f"min_area = {MIN_AREA}\n")
        fw.write(f"close_kernel = {CLOSE_KERNEL}\n")
        fw.write(f"use_opening = {USE_OPENING}\n")
        fw.write(f"open_kernel = {OPEN_KERNEL}\n")
        fw.write(f"use_smooth_display = {USE_SMOOTH_DISPLAY}\n")
        fw.write(f"display_close_kernel = {DISPLAY_CLOSE_KERNEL}\n")
        fw.write(f"display_median_kernel = {DISPLAY_MEDIAN_KERNEL}\n")
        fw.write(f"fill_small_holes = {FILL_SMALL_HOLES}\n")
        fw.write(f"max_hole_area = {MAX_HOLE_AREA}\n")
        fw.write(f"display_min_area = {DISPLAY_MIN_AREA}\n")
        fw.write("=" * 80 + "\n")

        for idx, row in enumerate(selected_records, start=1):
            image_path = Path(row["image_path"])
            mask_path = Path(row["mask_road_path"])

            sample_id = get_sample_id(row)

            image_rgb, gt_mask, raw_mask, clean_mask, smooth_mask = predict_one(
                model=model,
                image_path=image_path,
                mask_path=mask_path,
                img_size=img_size,
            )

            raw_overlay = overlay_road_on_image(image_rgb, raw_mask, alpha=0.55)
            clean_overlay = overlay_road_on_image(image_rgb, clean_mask, alpha=0.55)
            smooth_overlay = overlay_road_on_image(image_rgb, smooth_mask, alpha=0.55)

            raw_mask_path = OUTPUT_RAW_MASK / f"{sample_id}_raw_road_mask.png"
            clean_mask_path = OUTPUT_CLEAN_MASK / f"{sample_id}_clean_road_mask.png"
            smooth_mask_path = OUTPUT_SMOOTH_MASK / f"{sample_id}_smooth_display_road_mask.png"

            raw_overlay_path = OUTPUT_RAW_OVERLAY / f"{sample_id}_raw_overlay.png"
            clean_overlay_path = OUTPUT_CLEAN_OVERLAY / f"{sample_id}_clean_overlay.png"
            smooth_overlay_path = OUTPUT_SMOOTH_OVERLAY / f"{sample_id}_smooth_display_overlay.png"

            compare_path = OUTPUT_COMPARE / f"{sample_id}_raw_clean_smooth_compare.png"

            save_gray_mask(raw_mask, raw_mask_path)
            save_gray_mask(clean_mask, clean_mask_path)
            save_gray_mask(smooth_mask, smooth_mask_path)

            save_color_image(raw_overlay, raw_overlay_path)
            save_color_image(clean_overlay, clean_overlay_path)
            save_color_image(smooth_overlay, smooth_overlay_path)

            draw_compare_figure(
                image_rgb=image_rgb,
                gt_mask=gt_mask,
                raw_mask=raw_mask,
                clean_mask=clean_mask,
                smooth_mask=smooth_mask,
                raw_overlay=raw_overlay,
                clean_overlay=clean_overlay,
                smooth_overlay=smooth_overlay,
                save_path=compare_path,
                sample_id=sample_id,
            )

            raw_pixels = int(raw_mask.sum())
            clean_pixels = int(clean_mask.sum())
            smooth_pixels = int(smooth_mask.sum())

            print(
                f"[{idx}/{len(selected_records)}] {sample_id} "
                f"raw_pixels={raw_pixels}, "
                f"clean_pixels={clean_pixels}, "
                f"smooth_pixels={smooth_pixels}"
            )

            fw.write(f"[{idx}] {sample_id}\n")
            fw.write(f"image_path = {image_path}\n")
            fw.write(f"mask_path = {mask_path}\n")
            fw.write(f"raw_mask = {raw_mask_path}\n")
            fw.write(f"clean_mask = {clean_mask_path}\n")
            fw.write(f"smooth_mask = {smooth_mask_path}\n")
            fw.write(f"raw_overlay = {raw_overlay_path}\n")
            fw.write(f"clean_overlay = {clean_overlay_path}\n")
            fw.write(f"smooth_overlay = {smooth_overlay_path}\n")
            fw.write(f"compare = {compare_path}\n")
            fw.write(f"raw_pixels = {raw_pixels}\n")
            fw.write(f"clean_pixels = {clean_pixels}\n")
            fw.write(f"smooth_pixels = {smooth_pixels}\n")
            fw.write("-" * 80 + "\n")

    print("=" * 80)
    print("道路预测后处理完成")
    print(f"对比图目录: {OUTPUT_COMPARE}")
    print(f"raw mask 目录: {OUTPUT_RAW_MASK}")
    print(f"clean mask 目录: {OUTPUT_CLEAN_MASK}")
    print(f"smooth display mask 目录: {OUTPUT_SMOOTH_MASK}")
    print(f"raw overlay 目录: {OUTPUT_RAW_OVERLAY}")
    print(f"clean overlay 目录: {OUTPUT_CLEAN_OVERLAY}")
    print(f"smooth display overlay 目录: {OUTPUT_SMOOTH_OVERLAY}")
    print(f"结果记录: {result_txt}")
    print("=" * 80)


if __name__ == "__main__":
    main()
