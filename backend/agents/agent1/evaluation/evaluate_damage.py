# -*- coding: utf-8 -*-
"""
09_predict_damage_7ch_test.py

作用：
使用“建筑物二值模型 + 7通道损伤等级模型”对测试集样本进行预测。

流程：
1. 输入灾前图 pre_image
2. building_unet_medium_best.pth 预测建筑物二值 mask
3. 将 pre_image + post_image + pred_building_mask 拼成 7 通道
4. damage_unet_7ch_best.pth 预测灾后损伤等级 mask
5. 非建筑区域强制设为背景 0
6. 输出五联图：
   灾前图 | 灾后图 | 真实损伤mask | 预测损伤mask | 预测叠加图
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

PROJECT_ROOT = workspace_root()

DATA_DIR = PROJECT_ROOT / "data" / "processed"
TEST_CSV = DATA_DIR / "splits" / "test.csv"

BUILDING_CKPT = PROJECT_ROOT / "agent1_visual_evidence" / "checkpoints" / "building_unet_medium_best.pth"
DAMAGE_CKPT = PROJECT_ROOT / "agent1_visual_evidence" / "checkpoints" / "damage_unet_7ch_best.pth"

OUTPUT_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "outputs" / "damage_7ch_pred_test"
PRED_BUILDING_DIR = OUTPUT_DIR / "pred_building_mask"
PRED_DAMAGE_DIR = OUTPUT_DIR / "pred_damage_mask"
PRED_COLOR_DIR = OUTPUT_DIR / "pred_damage_color"
GT_COLOR_DIR = OUTPUT_DIR / "gt_damage_color"
OVERLAY_DIR = OUTPUT_DIR / "overlay"
VIS_DIR = OUTPUT_DIR / "visual_compare"

for d in [PRED_BUILDING_DIR, PRED_DAMAGE_DIR, PRED_COLOR_DIR, GT_COLOR_DIR, OVERLAY_DIR, VIS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

RESULT_TXT = OUTPUT_DIR / "damage_7ch_pred_result.txt"


# ============================================================
# 2. 参数设置
# ============================================================

NUM_TEST_SAMPLES = 20          # 建议先预测 20 张
PREFER_DAMAGE_SAMPLE = True    # 优先选择含 2/3/4 损伤类别的测试样本

IMG_SIZE = 512
BUILDING_THRESHOLD = 0.5
NUM_CLASSES = 5

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
# 4. 损伤等级颜色
# ============================================================

DAMAGE_COLORS = {
    0: (0, 0, 0),          # 背景：黑色
    1: (0, 255, 0),        # 无损：绿色
    2: (255, 255, 0),      # 轻微损伤：黄色
    3: (255, 165, 0),      # 严重损伤：橙色
    4: (255, 0, 0),        # 摧毁：红色
}

DAMAGE_NAMES = {
    0: "background",
    1: "no_damage",
    2: "minor_damage",
    3: "major_damage",
    4: "destroyed",
}


# ============================================================
# 5. 建筑物二值模型结构：SimpleUNet
# ============================================================

class DoubleConv(nn.Module):
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
    建筑物二值分割模型
    输入：3 通道灾前 RGB
    输出：1 通道建筑 logits
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

        return self.out_conv(d1)


# ============================================================
# 6. 7通道损伤等级模型结构
# ============================================================

class DamageUNet(nn.Module):
    """
    7 通道损伤等级分割模型
    输入：pre RGB + post RGB + building mask = 7 通道
    输出：5 类 logits
    """

    def __init__(self, in_channels=7, num_classes=5, base_channels=32):
        super(DamageUNet, self).__init__()

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

        self.out_conv = nn.Conv2d(base_channels, num_classes, kernel_size=1)

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

        return self.out_conv(d1)


# ============================================================
# 7. 工具函数
# ============================================================

def safe_torch_load(path, device):
    """兼容新版 PyTorch 的 checkpoint 加载方式"""
    try:
        return torch.load(path, map_location=device, weights_only=False)
    except TypeError:
        return torch.load(path, map_location=device)


def read_csv_records(csv_path):
    records = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    return records


def image_to_tensor_rgb(img):
    arr = np.array(img).astype(np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))  # H,W,C -> C,H,W
    return torch.from_numpy(arr).unsqueeze(0)


def load_pre_post(pre_path, post_path, img_size):
    pre_img = Image.open(pre_path).convert("RGB")
    post_img = Image.open(post_path).convert("RGB")

    pre_resized = pre_img.resize((img_size, img_size), RESAMPLE_BILINEAR)
    post_resized = post_img.resize((img_size, img_size), RESAMPLE_BILINEAR)

    return pre_img, post_img, pre_resized, post_resized


def predict_building_mask(building_model, pre_img):
    """
    用建筑模型预测 building mask。
    输出：
    building_binary: H,W，0/1
    """
    x = image_to_tensor_rgb(pre_img).to(DEVICE)

    with torch.no_grad():
        logits = building_model(x)
        prob = torch.sigmoid(logits)

    prob_np = prob.squeeze().cpu().numpy()
    building_binary = (prob_np > BUILDING_THRESHOLD).astype(np.uint8)

    return building_binary


def make_7ch_input(pre_img, post_img, building_binary):
    """
    拼接 7 通道输入：
    pre RGB + post RGB + building mask
    """
    pre_arr = np.array(pre_img).astype(np.float32) / 255.0
    post_arr = np.array(post_img).astype(np.float32) / 255.0
    building_arr = building_binary.astype(np.float32)
    building_arr = np.expand_dims(building_arr, axis=2)  # H,W,1

    x = np.concatenate([pre_arr, post_arr, building_arr], axis=2)  # H,W,7
    x = np.transpose(x, (2, 0, 1))  # 7,H,W

    return torch.from_numpy(x).unsqueeze(0)


def predict_damage_mask(damage_model, input_7ch, building_binary):
    """
    用 7通道模型预测损伤等级 mask。
    并强制非建筑区域为背景 0。
    """
    input_7ch = input_7ch.to(DEVICE)

    with torch.no_grad():
        logits = damage_model(input_7ch)
        pred = torch.argmax(logits, dim=1)

    pred_np = pred.squeeze(0).cpu().numpy().astype(np.uint8)

    # 建筑约束后处理：非建筑区域强制为背景
    pred_np[building_binary == 0] = 0

    return pred_np


def load_gt_damage_mask(mask_path, img_size):
    mask = Image.open(mask_path).convert("L")
    mask = mask.resize((img_size, img_size), RESAMPLE_NEAREST)
    arr = np.array(mask).astype(np.uint8)
    arr[arr > 4] = 0
    return arr


def colorize_damage_mask(mask_arr):
    h, w = mask_arr.shape
    color = np.zeros((h, w, 3), dtype=np.uint8)

    for cls_id, rgb in DAMAGE_COLORS.items():
        color[mask_arr == cls_id] = rgb

    return Image.fromarray(color)


def building_mask_to_visual(mask_binary):
    out = np.zeros((mask_binary.shape[0], mask_binary.shape[1], 3), dtype=np.uint8)
    out[mask_binary > 0] = (255, 255, 255)
    return Image.fromarray(out)


def overlay_damage_on_post(post_img, color_mask, alpha=0.45):
    post_arr = np.array(post_img).astype(np.float32)
    mask_arr = np.array(color_mask).astype(np.float32)

    valid = np.sum(mask_arr, axis=2) > 0

    out = post_arr.copy()
    out[valid] = post_arr[valid] * (1 - alpha) + mask_arr[valid] * alpha

    out = np.clip(out, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def calculate_iou_per_class(pred, gt, num_classes=5):
    ious = []

    for cls_id in range(num_classes):
        pred_cls = pred == cls_id
        gt_cls = gt == cls_id

        inter = np.logical_and(pred_cls, gt_cls).sum()
        union = np.logical_or(pred_cls, gt_cls).sum()

        if union == 0:
            iou = np.nan
        else:
            iou = (inter + 1.0) / (union + 1.0)

        ious.append(iou)

    return ious


def mean_ignore_nan(values):
    vals = [v for v in values if not np.isnan(v)]
    if len(vals) == 0:
        return 0.0
    return float(np.mean(vals))


def add_title(img, title, title_h=36):
    w, h = img.size

    canvas = Image.new("RGB", (w, h + title_h), (255, 255, 255))
    canvas.paste(img, (0, title_h))

    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((8, 10), title, fill=(0, 0, 0), font=font)

    return canvas


def make_compare_figure(pre_img, post_img, building_vis, gt_color, pred_color, overlay_img, out_path):
    """
    生成六联图：
    Pre | Post | Pred building | GT damage | Pred damage | Overlay
    """
    size = 512

    imgs = [
        add_title(pre_img.resize((size, size), RESAMPLE_BILINEAR), "Pre image"),
        add_title(post_img.resize((size, size), RESAMPLE_BILINEAR), "Post image"),
        add_title(building_vis.resize((size, size), RESAMPLE_NEAREST), "Pred building"),
        add_title(gt_color.resize((size, size), RESAMPLE_NEAREST), "GT damage"),
        add_title(pred_color.resize((size, size), RESAMPLE_NEAREST), "Pred damage"),
        add_title(overlay_img.resize((size, size), RESAMPLE_BILINEAR), "Pred overlay"),
    ]

    tile_w, tile_h = imgs[0].size

    canvas = Image.new("RGB", (tile_w * 6, tile_h), (255, 255, 255))

    for i, img in enumerate(imgs):
        canvas.paste(img, (tile_w * i, 0))

    canvas.save(out_path)


def has_damage_234(row):
    mask_path = DATA_DIR / row["post_damage_mask"]

    try:
        mask = Image.open(mask_path).convert("L")
        arr = np.array(mask)
        return np.any((arr == 2) | (arr == 3) | (arr == 4))
    except Exception:
        return False


# ============================================================
# 8. 主程序
# ============================================================

def main():
    print("=" * 70)
    print("7通道损伤等级模型预测开始")
    print("=" * 70)
    print(f"设备：{DEVICE}")
    print(f"建筑模型：{BUILDING_CKPT}")
    print(f"损伤模型：{DAMAGE_CKPT}")
    print(f"测试集：{TEST_CSV}")
    print(f"输出目录：{OUTPUT_DIR}")
    print("=" * 70)

    if not BUILDING_CKPT.exists():
        raise FileNotFoundError(f"找不到建筑模型：{BUILDING_CKPT}")

    if not DAMAGE_CKPT.exists():
        raise FileNotFoundError(f"找不到损伤模型：{DAMAGE_CKPT}")

    # ---------- 加载建筑模型 ----------
    building_ckpt = safe_torch_load(BUILDING_CKPT, DEVICE)
    building_model = SimpleUNet(in_channels=3, out_channels=1, base_channels=32)
    building_model.load_state_dict(building_ckpt["model_state_dict"])
    building_model.to(DEVICE)
    building_model.eval()

    # ---------- 加载7通道损伤模型 ----------
    damage_ckpt = safe_torch_load(DAMAGE_CKPT, DEVICE)
    img_size = damage_ckpt.get("img_size", IMG_SIZE)

    damage_model = DamageUNet(in_channels=7, num_classes=NUM_CLASSES, base_channels=32)
    damage_model.load_state_dict(damage_ckpt["model_state_dict"])
    damage_model.to(DEVICE)
    damage_model.eval()

    print(f"模型输入尺寸：{img_size}")

    # ---------- 选择测试样本 ----------
    records = read_csv_records(TEST_CSV)
    random.shuffle(records)

    if PREFER_DAMAGE_SAMPLE:
        damage_records = [r for r in records if has_damage_234(r)]
        normal_records = [r for r in records if not has_damage_234(r)]

        random.shuffle(damage_records)
        random.shuffle(normal_records)

        selected_records = damage_records[:NUM_TEST_SAMPLES]

        if len(selected_records) < NUM_TEST_SAMPLES:
            need = NUM_TEST_SAMPLES - len(selected_records)
            selected_records += normal_records[:need]

        print(f"优先选择含 2/3/4 损伤样本，候选数：{len(damage_records)}")
    else:
        selected_records = records[:NUM_TEST_SAMPLES]

    print(f"实际预测样本数：{len(selected_records)}")

    result_lines = []
    result_lines.append("7通道损伤等级模型测试预测结果")
    result_lines.append("=" * 70)
    result_lines.append(f"建筑模型：{BUILDING_CKPT}")
    result_lines.append(f"损伤模型：{DAMAGE_CKPT}")
    result_lines.append(f"测试集：{TEST_CSV}")
    result_lines.append(f"样本数：{len(selected_records)}")
    result_lines.append("")

    miou_all_list = []
    miou_fg_list = []

    for idx, row in enumerate(selected_records, start=1):
        sample_id = row["sample_id"]
        disaster_type = row["disaster_type"]

        print(f"[{idx}/{len(selected_records)}] 正在预测：{sample_id}")

        pre_path = DATA_DIR / row["pre_image"]
        post_path = DATA_DIR / row["post_image"]
        gt_damage_path = DATA_DIR / row["post_damage_mask"]

        pre_original, post_original, pre_img, post_img = load_pre_post(pre_path, post_path, img_size)

        # 1. 先预测建筑物二值 mask
        pred_building = predict_building_mask(building_model, pre_img)

        # 2. 拼接 7 通道输入
        input_7ch = make_7ch_input(pre_img, post_img, pred_building)

        # 3. 预测损伤等级 mask
        pred_damage = predict_damage_mask(damage_model, input_7ch, pred_building)

        # 4. 读取真实损伤 mask
        gt_damage = load_gt_damage_mask(gt_damage_path, img_size)

        # 5. 计算指标
        class_ious = calculate_iou_per_class(pred_damage, gt_damage, NUM_CLASSES)
        miou_all = mean_ignore_nan(class_ious)
        miou_fg = mean_ignore_nan(class_ious[1:])

        miou_all_list.append(miou_all)
        miou_fg_list.append(miou_fg)

        # 6. 可视化
        pred_building_vis = building_mask_to_visual(pred_building)
        gt_color = colorize_damage_mask(gt_damage)
        pred_color = colorize_damage_mask(pred_damage)
        overlay = overlay_damage_on_post(post_img, pred_color, alpha=0.45)

        # 7. 输出子目录
        for base_dir in [PRED_BUILDING_DIR, PRED_DAMAGE_DIR, PRED_COLOR_DIR, GT_COLOR_DIR, OVERLAY_DIR, VIS_DIR]:
            (base_dir / disaster_type).mkdir(parents=True, exist_ok=True)

        pred_building_path = PRED_BUILDING_DIR / disaster_type / f"{sample_id}_pred_building_mask.png"
        pred_damage_path = PRED_DAMAGE_DIR / disaster_type / f"{sample_id}_pred_damage_7ch_mask.png"
        pred_color_path = PRED_COLOR_DIR / disaster_type / f"{sample_id}_pred_damage_7ch_color.png"
        gt_color_path = GT_COLOR_DIR / disaster_type / f"{sample_id}_gt_damage_color.png"
        overlay_path = OVERLAY_DIR / disaster_type / f"{sample_id}_pred_overlay.png"
        vis_path = VIS_DIR / disaster_type / f"{sample_id}_damage_7ch_compare.png"

        Image.fromarray((pred_building * 255).astype(np.uint8)).save(pred_building_path)
        Image.fromarray(pred_damage.astype(np.uint8)).save(pred_damage_path)
        pred_color.save(pred_color_path)
        gt_color.save(gt_color_path)
        overlay.save(overlay_path)

        make_compare_figure(
            pre_img=pre_img,
            post_img=post_img,
            building_vis=pred_building_vis,
            gt_color=gt_color,
            pred_color=pred_color,
            overlay_img=overlay,
            out_path=vis_path
        )

        line = (
            f"{idx}. sample_id={sample_id}, disaster_type={disaster_type}, "
            f"mIoU_all={miou_all:.4f}, mIoU_fg={miou_fg:.4f}, "
            f"IoU_bg={class_ious[0]:.4f}, "
            f"IoU_no={class_ious[1]:.4f}, "
            f"IoU_minor={class_ious[2]:.4f}, "
            f"IoU_major={class_ious[3]:.4f}, "
            f"IoU_destroyed={class_ious[4]:.4f}"
        )

        print("  " + line)
        result_lines.append(line)
        result_lines.append(f"   compare={vis_path}")
        result_lines.append("")

    avg_miou_all = sum(miou_all_list) / len(miou_all_list) if len(miou_all_list) > 0 else 0.0
    avg_miou_fg = sum(miou_fg_list) / len(miou_fg_list) if len(miou_fg_list) > 0 else 0.0

    result_lines.append("-" * 70)
    result_lines.append(f"平均 mIoU_all：{avg_miou_all:.4f}")
    result_lines.append(f"平均 mIoU_fg：{avg_miou_fg:.4f}")
    result_lines.append(f"六联对比图目录：{VIS_DIR}")
    result_lines.append("=" * 70)

    with open(RESULT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(result_lines))

    print("=" * 70)
    print("预测完成")
    print(f"平均 mIoU_all：{avg_miou_all:.4f}")
    print(f"平均 mIoU_fg：{avg_miou_fg:.4f}")
    print(f"结果文件：{RESULT_TXT}")
    print(f"六联对比图目录：{VIS_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
