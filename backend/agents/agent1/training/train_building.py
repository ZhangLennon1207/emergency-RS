# -*- coding: utf-8 -*-
"""
05_train_building_unet.py

作用：
训练灾前建筑物二值分割模型。

任务：
输入：pre_image 灾前遥感图像
输出：pre_building_mask 灾前建筑物二值掩码

数据来源：
data/processed/splits/train.csv
data/processed/splits/val.csv

mask 像素值：
原始 building_mask: 0 / 255
训练时转换为: 0 / 1

模型：
轻量 U-Net baseline

损失：
BCEWithLogitsLoss + Dice Loss

指标：
IoU / Dice
"""

from pathlib import Path
import csv
import time
import random

import numpy as np
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

from backend.agents.agent1.src.models import BuildingUNet
from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = workspace_root()

DATA_DIR = PROJECT_ROOT / "data" / "processed"
SPLIT_DIR = DATA_DIR / "splits"

TRAIN_CSV = SPLIT_DIR / "train.csv"
VAL_CSV = SPLIT_DIR / "val.csv"

CHECKPOINT_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "checkpoints"
LOG_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "logs"

CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

BEST_MODEL_PATH = CHECKPOINT_DIR /  "building_unet_medium_best.pth"
LAST_MODEL_PATH = CHECKPOINT_DIR / "building_unet_medium_last.pth"
LOG_PATH = LOG_DIR / "building_unet_medium_train_log.txt"

# ============================================================
# 2. 训练参数
# ============================================================

# 第一次建议先用 256，跑通后再改成 512
IMG_SIZE = 512

# 第一次先小样本调试，跑通后改成 None 使用全部数据
MAX_TRAIN_SAMPLES = 5000
MAX_VAL_SAMPLES = 1000

EPOCHS = 20
BATCH_SIZE = 2
LEARNING_RATE = 5e-4

# Windows 下建议先用 0，最稳定
NUM_WORKERS = 0

RANDOM_SEED = 2026
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)


# ============================================================
# 3. 设备设置
# ============================================================

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# 4. 图像缩放兼容写法
# ============================================================

try:
    RESAMPLE_BILINEAR = Image.Resampling.BILINEAR
    RESAMPLE_NEAREST = Image.Resampling.NEAREST
except AttributeError:
    RESAMPLE_BILINEAR = Image.BILINEAR
    RESAMPLE_NEAREST = Image.NEAREST


# ============================================================
# 5. 读取 csv
# ============================================================

def read_csv_records(csv_path, max_samples=None):
    records = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    random.shuffle(records)

    if max_samples is not None:
        records = records[:max_samples]

    return records


# ============================================================
# 6. 数据集定义
# ============================================================

class BuildingSegDataset(Dataset):
    """
    建筑物二值分割数据集

    输入：
    pre_image

    标签：
    pre_building_mask
    """

    def __init__(self, records, data_dir, img_size=512):
        self.records = records
        self.data_dir = data_dir
        self.img_size = img_size

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        row = self.records[idx]

        image_path = self.data_dir / row["pre_image"]
        mask_path = self.data_dir / row["pre_building_mask"]

        # ---------- 读取灾前图 ----------
        image = Image.open(image_path).convert("RGB")
        image = image.resize((self.img_size, self.img_size), RESAMPLE_BILINEAR)
        image = np.array(image).astype(np.float32) / 255.0

        # HWC -> CHW
        image = np.transpose(image, (2, 0, 1))

        # ---------- 读取建筑物二值 mask ----------
        mask = Image.open(mask_path).convert("L")
        mask = mask.resize((self.img_size, self.img_size), RESAMPLE_NEAREST)
        mask = np.array(mask).astype(np.float32)

        # 原始值 0 / 255 转成 0 / 1
        mask = (mask > 0).astype(np.float32)

        # 增加 channel 维度：1 × H × W
        mask = np.expand_dims(mask, axis=0)

        image_tensor = torch.from_numpy(image)
        mask_tensor = torch.from_numpy(mask)

        return image_tensor, mask_tensor


# ============================================================
# 7. U-Net 模型
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
# 8. Loss 和指标
# ============================================================

def dice_loss_with_logits(logits, targets, smooth=1.0):
    """
    Dice Loss
    logits: 模型原始输出
    targets: 0/1 标签
    """
    probs = torch.sigmoid(logits)

    probs = probs.view(probs.size(0), -1)
    targets = targets.view(targets.size(0), -1)

    intersection = (probs * targets).sum(dim=1)
    union = probs.sum(dim=1) + targets.sum(dim=1)

    dice = (2.0 * intersection + smooth) / (union + smooth)

    return 1.0 - dice.mean()


def combined_loss(logits, targets):
    """
    BCEWithLogitsLoss + Dice Loss
    """
    bce = nn.functional.binary_cross_entropy_with_logits(logits, targets)
    dice = dice_loss_with_logits(logits, targets)

    return bce + dice


@torch.no_grad()
def calculate_metrics(logits, targets, threshold=0.5):
    """
    计算 IoU 和 Dice
    """
    probs = torch.sigmoid(logits)
    preds = (probs > threshold).float()

    preds = preds.view(preds.size(0), -1)
    targets = targets.view(targets.size(0), -1)

    intersection = (preds * targets).sum(dim=1)
    pred_sum = preds.sum(dim=1)
    target_sum = targets.sum(dim=1)

    union = pred_sum + target_sum - intersection

    iou = (intersection + 1.0) / (union + 1.0)
    dice = (2.0 * intersection + 1.0) / (pred_sum + target_sum + 1.0)

    return iou.mean().item(), dice.mean().item()


# ============================================================
# 9. 训练一个 epoch
# ============================================================

def train_one_epoch(model, loader, optimizer):
    model.train()

    total_loss = 0.0
    total_iou = 0.0
    total_dice = 0.0
    total_batches = 0

    for images, masks in loader:
        images = images.to(DEVICE)
        masks = masks.to(DEVICE)

        optimizer.zero_grad()

        logits = model(images)
        loss = combined_loss(logits, masks)

        loss.backward()
        optimizer.step()

        iou, dice = calculate_metrics(logits, masks)

        total_loss += loss.item()
        total_iou += iou
        total_dice += dice
        total_batches += 1

    avg_loss = total_loss / total_batches
    avg_iou = total_iou / total_batches
    avg_dice = total_dice / total_batches

    return avg_loss, avg_iou, avg_dice


# ============================================================
# 10. 验证一个 epoch
# ============================================================

@torch.no_grad()
def validate_one_epoch(model, loader):
    model.eval()

    total_loss = 0.0
    total_iou = 0.0
    total_dice = 0.0
    total_batches = 0

    for images, masks in loader:
        images = images.to(DEVICE)
        masks = masks.to(DEVICE)

        logits = model(images)
        loss = combined_loss(logits, masks)

        iou, dice = calculate_metrics(logits, masks)

        total_loss += loss.item()
        total_iou += iou
        total_dice += dice
        total_batches += 1

    avg_loss = total_loss / total_batches
    avg_iou = total_iou / total_batches
    avg_dice = total_dice / total_batches

    return avg_loss, avg_iou, avg_dice


# ============================================================
# 11. 主训练流程
# ============================================================

def main():
    print("=" * 70)
    print("灾前建筑物二值分割模型训练开始")
    print("=" * 70)
    print(f"项目根目录：{PROJECT_ROOT}")
    print(f"训练集：{TRAIN_CSV}")
    print(f"验证集：{VAL_CSV}")
    print(f"设备：{DEVICE}")
    print(f"IMG_SIZE = {IMG_SIZE}")
    print(f"BATCH_SIZE = {BATCH_SIZE}")
    print(f"EPOCHS = {EPOCHS}")
    print(f"MAX_TRAIN_SAMPLES = {MAX_TRAIN_SAMPLES}")
    print(f"MAX_VAL_SAMPLES = {MAX_VAL_SAMPLES}")
    print("=" * 70)

    train_records = read_csv_records(TRAIN_CSV, max_samples=MAX_TRAIN_SAMPLES)
    val_records = read_csv_records(VAL_CSV, max_samples=MAX_VAL_SAMPLES)

    print(f"实际训练样本数：{len(train_records)}")
    print(f"实际验证样本数：{len(val_records)}")

    train_dataset = BuildingSegDataset(train_records, DATA_DIR, img_size=IMG_SIZE)
    val_dataset = BuildingSegDataset(val_records, DATA_DIR, img_size=IMG_SIZE)

    train_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=torch.cuda.is_available(),
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=torch.cuda.is_available(),
    )

    model = BuildingUNet(in_channels=3, out_channels=1, base_channels=32)
    model = model.to(DEVICE)

    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

    best_val_iou = -1.0

    with open(LOG_PATH, "w", encoding="utf-8") as log_file:
        log_file.write("epoch,train_loss,train_iou,train_dice,val_loss,val_iou,val_dice,time_sec\n")

    for epoch in range(1, EPOCHS + 1):
        start_time = time.time()

        train_loss, train_iou, train_dice = train_one_epoch(model, train_loader, optimizer)
        val_loss, val_iou, val_dice = validate_one_epoch(model, val_loader)

        elapsed = time.time() - start_time

        line = (
            f"Epoch [{epoch}/{EPOCHS}] "
            f"train_loss={train_loss:.4f}, train_iou={train_iou:.4f}, train_dice={train_dice:.4f} | "
            f"val_loss={val_loss:.4f}, val_iou={val_iou:.4f}, val_dice={val_dice:.4f} | "
            f"time={elapsed:.1f}s"
        )

        print(line)

        with open(LOG_PATH, "a", encoding="utf-8") as log_file:
            log_file.write(
                f"{epoch},{train_loss:.6f},{train_iou:.6f},{train_dice:.6f},"
                f"{val_loss:.6f},{val_iou:.6f},{val_dice:.6f},{elapsed:.2f}\n"
            )

        # 保存最后一轮模型
        torch.save(
            {
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_iou": val_iou,
                "val_dice": val_dice,
                "img_size": IMG_SIZE,
            },
            LAST_MODEL_PATH,
        )

        # 保存验证 IoU 最好的模型
        if val_iou > best_val_iou:
            best_val_iou = val_iou

            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "val_iou": val_iou,
                    "val_dice": val_dice,
                    "img_size": IMG_SIZE,
                },
                BEST_MODEL_PATH,
            )

            print(f"  已保存最佳模型：{BEST_MODEL_PATH}, best_val_iou={best_val_iou:.4f}")

    print("=" * 70)
    print("训练完成")
    print(f"最佳模型：{BEST_MODEL_PATH}")
    print(f"最后模型：{LAST_MODEL_PATH}")
    print(f"训练日志：{LOG_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
