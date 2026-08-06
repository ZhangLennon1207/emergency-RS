# -*- coding: utf-8 -*-
"""
06_predict_building_unet_test5.py

作用：
使用 building_unet_best.pth 对测试集中的 5 张灾前遥感图像进行建筑物二值分割预测。

输入：
1. data/processed/splits/test.csv
2. agent1_visual_evidence/checkpoints/building_unet_best.pth

输出：
1. 预测建筑物二值 mask
2. 预测概率图
3. 可视化对比图
4. 单样本 IoU / Dice 结果
"""

from pathlib import Path
import csv
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import torch
import torch.nn as nn

from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

# 如果你的项目路径不是这个，请改这里
PROJECT_ROOT = workspace_root()

DATA_DIR = PROJECT_ROOT / "data" / "processed"
TEST_CSV = DATA_DIR / "splits" / "test.csv"

CHECKPOINT_PATH = PROJECT_ROOT / "agent1_visual_evidence" / "checkpoints" / "building_unet_medium_best.pth"

OUTPUT_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "outputs" / "building_pred_medium_test5"
PRED_MASK_DIR = OUTPUT_DIR / "pred_mask"
PRED_PROB_DIR = OUTPUT_DIR / "pred_prob"
VIS_DIR = OUTPUT_DIR / "visual_compare"

PRED_MASK_DIR.mkdir(parents=True, exist_ok=True)
PRED_PROB_DIR.mkdir(parents=True, exist_ok=True)
VIS_DIR.mkdir(parents=True, exist_ok=True)

RESULT_TXT = OUTPUT_DIR / "building_pred_test5_result.txt"


# ============================================================
# 2. 预测参数
# ============================================================

NUM_TEST_SAMPLES = 5
THRESHOLD = 0.5
RANDOM_SEED = 2026

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)


# ============================================================
# 3. 图像缩放兼容写法
# ============================================================

try:
    RESAMPLE_BILINEAR = Image.Resampling.BILINEAR
    RESAMPLE_NEAREST = Image.Resampling.NEAREST
except AttributeError:
    RESAMPLE_BILINEAR = Image.BILINEAR
    RESAMPLE_NEAREST = Image.NEAREST


# ============================================================
# 4. 模型结构：必须和训练脚本保持一致
# ============================================================

class DoubleConv(nn.Module):
    """两层卷积"""

    def __init__(self, in_channels, out_channels):
        super(DoubleConv, self).__init__()

        self.net = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),

            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.net(x)


class SimpleUNet(nn.Module):
    """
    轻量 U-Net
    输入：3 通道 RGB 图像
    输出：1 通道建筑概率 logits
    """

    def __init__(self, in_channels=3, out_channels=1, base_channels=32):
        super(SimpleUNet, self).__init__()

        self.enc1 = DoubleConv(in_channels, base_channels)
        self.pool1 = nn.MaxPool2d(2)

        self.enc2 = DoubleConv(base_channels, base_channels * 2)
        self.pool2 = nn.MaxPool2d(2)

        self.enc3 = DoubleConv(base_channels * 2, base_channels * 4)
        self.pool3 = nn.MaxPool2d(2)

        self.bottleneck = DoubleConv(base_channels * 4, base_channels * 8)

        self.up3 = nn.ConvTranspose2d(base_channels * 8, base_channels * 4, kernel_size=2, stride=2)
        self.dec3 = DoubleConv(base_channels * 8, base_channels * 4)

        self.up2 = nn.ConvTranspose2d(base_channels * 4, base_channels * 2, kernel_size=2, stride=2)
        self.dec2 = DoubleConv(base_channels * 4, base_channels * 2)

        self.up1 = nn.ConvTranspose2d(base_channels * 2, base_channels, kernel_size=2, stride=2)
        self.dec1 = DoubleConv(base_channels * 2, base_channels)

        self.out_conv = nn.Conv2d(base_channels, out_channels, kernel_size=1)

    def forward(self, x):
        e1 = self.enc1(x)

        e2 = self.enc2(self.pool1(e1))

        e3 = self.enc3(self.pool2(e2))

        b = self.bottleneck(self.pool3(e3))

        d3 = self.up3(b)
        d3 = torch.cat([d3, e3], dim=1)
        d3 = self.dec3(d3)

        d2 = self.up2(d3)
        d2 = torch.cat([d2, e2], dim=1)
        d2 = self.dec2(d2)

        d1 = self.up1(d2)
        d1 = torch.cat([d1, e1], dim=1)
        d1 = self.dec1(d1)

        out = self.out_conv(d1)

        return out


# ============================================================
# 5. 工具函数
# ============================================================

def read_csv_records(csv_path):
    """读取 csv"""
    records = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    return records


def load_image_as_tensor(image_path, img_size):
    """
    读取 RGB 图像，并转成模型输入 tensor。
    输出形状：1 × 3 × H × W
    """
    image = Image.open(image_path).convert("RGB")
    image_resized = image.resize((img_size, img_size), RESAMPLE_BILINEAR)

    arr = np.array(image_resized).astype(np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))

    tensor = torch.from_numpy(arr).unsqueeze(0)

    return image, image_resized, tensor


def load_gt_mask(mask_path, img_size):
    """
    读取真实建筑 mask。
    原始像素值：0 / 255
    转成：0 / 1
    """
    mask = Image.open(mask_path).convert("L")
    mask_resized = mask.resize((img_size, img_size), RESAMPLE_NEAREST)

    arr = np.array(mask_resized)
    binary = (arr > 0).astype(np.uint8)

    return mask, binary


def predict_one(model, image_tensor):
    """
    单张图像预测。
    输出：
    prob: 0~1 概率图
    pred: 0/1 二值图
    """
    image_tensor = image_tensor.to(DEVICE)

    with torch.no_grad():
        logits = model(image_tensor)
        prob = torch.sigmoid(logits)

    prob_np = prob.squeeze().cpu().numpy()
    pred_np = (prob_np > THRESHOLD).astype(np.uint8)

    return prob_np, pred_np


def calculate_iou_dice(pred, gt):
    """
    计算 IoU 和 Dice。
    pred, gt 都是 0/1 二值数组。
    """
    pred = pred.astype(np.uint8)
    gt = gt.astype(np.uint8)

    intersection = np.logical_and(pred == 1, gt == 1).sum()
    union = np.logical_or(pred == 1, gt == 1).sum()

    pred_sum = (pred == 1).sum()
    gt_sum = (gt == 1).sum()

    iou = (intersection + 1.0) / (union + 1.0)
    dice = (2.0 * intersection + 1.0) / (pred_sum + gt_sum + 1.0)

    return float(iou), float(dice)


def binary_mask_to_visual(mask_binary):
    """
    将 0/1 mask 转成黑白 RGB 图。
    0 = 黑色
    1 = 白色
    """
    visual = np.zeros((mask_binary.shape[0], mask_binary.shape[1], 3), dtype=np.uint8)
    visual[mask_binary > 0] = (255, 255, 255)

    return Image.fromarray(visual)


def prob_to_image(prob):
    """
    将概率图 0~1 转成灰度图 0~255。
    """
    prob_img = (prob * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(prob_img)


def overlay_pred_on_image(image, pred_binary, alpha=0.45):
    """
    将预测建筑 mask 叠加到灾前图上。
    预测建筑区域用青色显示。
    """
    img_arr = np.array(image).astype(np.float32)

    color_mask = np.zeros_like(img_arr, dtype=np.float32)
    color_mask[pred_binary > 0] = (0, 255, 255)

    valid = pred_binary > 0

    out = img_arr.copy()
    out[valid] = img_arr[valid] * (1 - alpha) + color_mask[valid] * alpha

    out = np.clip(out, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def add_title(img, title, title_h=36):
    """
    给图片加标题。
    """
    w, h = img.size

    new_img = Image.new("RGB", (w, h + title_h), (255, 255, 255))
    new_img.paste(img, (0, title_h))

    draw = ImageDraw.Draw(new_img)
    font = ImageFont.load_default()
    draw.text((8, 10), title, fill=(0, 0, 0), font=font)

    return new_img


def make_compare_figure(pre_img, gt_visual, pred_visual, overlay_img, out_path):
    """
    生成四联图：
    灾前图 | 真实建筑 mask | 预测建筑 mask | 预测叠加图
    """
    size = 512

    pre_show = add_title(pre_img.resize((size, size), RESAMPLE_BILINEAR), "Pre image")
    gt_show = add_title(gt_visual.resize((size, size), RESAMPLE_NEAREST), "GT building mask")
    pred_show = add_title(pred_visual.resize((size, size), RESAMPLE_NEAREST), "Pred building mask")
    overlay_show = add_title(overlay_img.resize((size, size), RESAMPLE_BILINEAR), "Pred overlay")

    tile_w, tile_h = pre_show.size

    canvas = Image.new("RGB", (tile_w * 4, tile_h), (255, 255, 255))
    canvas.paste(pre_show, (0, 0))
    canvas.paste(gt_show, (tile_w, 0))
    canvas.paste(pred_show, (tile_w * 2, 0))
    canvas.paste(overlay_show, (tile_w * 3, 0))

    canvas.save(out_path)


# ============================================================
# 6. 主程序
# ============================================================

def main():
    print("=" * 70)
    print("使用 building_unet_best.pth 对测试集 5 张图进行预测")
    print("=" * 70)
    print(f"设备：{DEVICE}")
    print(f"测试集：{TEST_CSV}")
    print(f"模型权重：{CHECKPOINT_PATH}")
    print(f"输出目录：{OUTPUT_DIR}")
    print("=" * 70)

    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(f"找不到模型权重：{CHECKPOINT_PATH}")

    if not TEST_CSV.exists():
        raise FileNotFoundError(f"找不到 test.csv：{TEST_CSV}")

    # ---------- 加载模型权重 ----------
    checkpoint = torch.load(CHECKPOINT_PATH, map_location=DEVICE)

    img_size = checkpoint.get("img_size", 512)
    print(f"模型训练时图像尺寸 img_size = {img_size}")

    model = SimpleUNet(in_channels=3, out_channels=1, base_channels=32)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(DEVICE)
    model.eval()

    # ---------- 读取测试集 ----------
    test_records = read_csv_records(TEST_CSV)

    random.shuffle(test_records)
    selected_records = test_records[:NUM_TEST_SAMPLES]

    result_lines = []
    result_lines.append("建筑物二值分割模型测试集 5 张图预测结果")
    result_lines.append("=" * 70)
    result_lines.append(f"模型权重：{CHECKPOINT_PATH}")
    result_lines.append(f"测试集：{TEST_CSV}")
    result_lines.append(f"阈值：{THRESHOLD}")
    result_lines.append(f"图像尺寸：{img_size}")
    result_lines.append("")

    iou_list = []
    dice_list = []

    for idx, row in enumerate(selected_records, start=1):
        sample_id = row["sample_id"]
        disaster_type = row["disaster_type"]

        pre_image_path = DATA_DIR / row["pre_image"]
        gt_mask_path = DATA_DIR / row["pre_building_mask"]

        print(f"[{idx}/{NUM_TEST_SAMPLES}] 正在预测：{sample_id}")

        # 读取图像和标签
        pre_original, pre_resized, image_tensor = load_image_as_tensor(pre_image_path, img_size)
        gt_original, gt_binary = load_gt_mask(gt_mask_path, img_size)

        # 模型预测
        prob, pred_binary = predict_one(model, image_tensor)

        # 指标
        iou, dice = calculate_iou_dice(pred_binary, gt_binary)

        iou_list.append(iou)
        dice_list.append(dice)

        # 输出路径
        disaster_mask_dir = PRED_MASK_DIR / disaster_type
        disaster_prob_dir = PRED_PROB_DIR / disaster_type
        disaster_vis_dir = VIS_DIR / disaster_type

        disaster_mask_dir.mkdir(parents=True, exist_ok=True)
        disaster_prob_dir.mkdir(parents=True, exist_ok=True)
        disaster_vis_dir.mkdir(parents=True, exist_ok=True)

        pred_mask_path = disaster_mask_dir / f"{sample_id}_pred_building_mask.png"
        pred_prob_path = disaster_prob_dir / f"{sample_id}_pred_building_prob.png"
        vis_path = disaster_vis_dir / f"{sample_id}_building_compare.png"

        # 保存预测 mask：0/255
        pred_mask_255 = (pred_binary * 255).astype(np.uint8)
        Image.fromarray(pred_mask_255).save(pred_mask_path)

        # 保存概率图
        prob_to_image(prob).save(pred_prob_path)

        # 可视化
        gt_visual = binary_mask_to_visual(gt_binary)
        pred_visual = binary_mask_to_visual(pred_binary)
        overlay_img = overlay_pred_on_image(pre_resized, pred_binary)

        make_compare_figure(
            pre_img=pre_resized,
            gt_visual=gt_visual,
            pred_visual=pred_visual,
            overlay_img=overlay_img,
            out_path=vis_path,
        )

        line = (
            f"{idx}. sample_id={sample_id}, disaster_type={disaster_type}, "
            f"IoU={iou:.4f}, Dice={dice:.4f}, "
            f"pred_mask={pred_mask_path}"
        )

        result_lines.append(line)
        print("  " + line)

    avg_iou = sum(iou_list) / len(iou_list) if len(iou_list) > 0 else 0
    avg_dice = sum(dice_list) / len(dice_list) if len(dice_list) > 0 else 0

    result_lines.append("")
    result_lines.append("-" * 70)
    result_lines.append(f"5 张测试图平均 IoU：{avg_iou:.4f}")
    result_lines.append(f"5 张测试图平均 Dice：{avg_dice:.4f}")
    result_lines.append(f"预测 mask 输出目录：{PRED_MASK_DIR}")
    result_lines.append(f"预测概率图输出目录：{PRED_PROB_DIR}")
    result_lines.append(f"可视化对比图输出目录：{VIS_DIR}")
    result_lines.append("=" * 70)

    with open(RESULT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(result_lines))

    print("=" * 70)
    print("预测完成")
    print(f"平均 IoU：{avg_iou:.4f}")
    print(f"平均 Dice：{avg_dice:.4f}")
    print(f"结果文件：{RESULT_TXT}")
    print(f"可视化对比图目录：{VIS_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
