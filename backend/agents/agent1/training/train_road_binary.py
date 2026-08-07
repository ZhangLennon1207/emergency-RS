# -*- coding: utf-8 -*-
"""
13_train_road_unet.py

作用：
1. 读取 OpenEarthMap 道路二值数据集；
2. 训练道路二值分割 U-Net；
3. 输出 road_unet_best.pth 和 road_unet_last.pth；
4. 记录训练日志。

类别：
0 = 背景/其他
1 = 道路
"""

import csv
import random
from pathlib import Path

import numpy as np
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

from backend.agents.agent1.src.models import RoadUNet as ProductionRoadUNet
from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径和训练参数
# ============================================================

PROJECT_ROOT = workspace_root()

TRAIN_CSV = PROJECT_ROOT / "data" / "openearthmap" / "processed" / "splits" / "train.csv"
VAL_CSV = PROJECT_ROOT / "data" / "openearthmap" / "processed" / "splits" / "val.csv"

CHECKPOINT_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "checkpoints"
LOG_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "logs"

CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

BEST_MODEL_PATH = CHECKPOINT_DIR / "road_unet_best.pth"
LAST_MODEL_PATH = CHECKPOINT_DIR / "road_unet_last.pth"
LOG_CSV = LOG_DIR / "road_unet_train_log.csv"

# 你之前已经用过 768，这里继续用 768
IMG_SIZE = 768

# 如果显存不够，把 BATCH_SIZE 改成 1
BATCH_SIZE = 2

EPOCHS = 20
LEARNING_RATE = 5e-4
NUM_WORKERS = 0

# 道路像素很少，所以正样本权重要高一些
# 如果后面发现道路预测太少，可以改成 12 或 15
# 如果发现到处都是道路，可以改成 5 或 6
POS_WEIGHT = 10.0

BASE_CHANNELS = 32

SEED = 42

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# 2. 固定随机种子
# ============================================================

def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# ============================================================
# 3. Dataset
# ============================================================

class RoadDataset(Dataset):
    def __init__(self, csv_path, img_size=768, is_train=True):
        self.csv_path = Path(csv_path)
        self.img_size = img_size
        self.is_train = is_train

        self.records = []

        with open(self.csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.records.append(row)

        print(f"读取 {self.csv_path}")
        print(f"样本数量: {len(self.records)}")

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        row = self.records[idx]

        image_path = Path(row["image_path"])
        mask_path = Path(row["mask_road_path"])

        if not image_path.exists():
            raise FileNotFoundError(f"找不到 image: {image_path}")

        if not mask_path.exists():
            raise FileNotFoundError(f"找不到 mask: {mask_path}")

        image = Image.open(image_path).convert("RGB")
        mask = Image.open(mask_path).convert("L")

        image = image.resize((self.img_size, self.img_size), Image.BILINEAR)
        mask = mask.resize((self.img_size, self.img_size), Image.NEAREST)

        image_np = np.array(image).astype(np.float32) / 255.0
        mask_np = np.array(mask).astype(np.float32)

        # 确保 mask 只有 0 和 1
        mask_np = (mask_np > 0).astype(np.float32)

        # 简单数据增强，只在训练集使用
        if self.is_train:
            if random.random() < 0.5:
                image_np = np.flip(image_np, axis=1).copy()
                mask_np = np.flip(mask_np, axis=1).copy()

            if random.random() < 0.5:
                image_np = np.flip(image_np, axis=0).copy()
                mask_np = np.flip(mask_np, axis=0).copy()

            # 随机旋转 0/90/180/270 度
            k = random.randint(0, 3)
            if k > 0:
                image_np = np.rot90(image_np, k, axes=(0, 1)).copy()
                mask_np = np.rot90(mask_np, k, axes=(0, 1)).copy()

        # HWC -> CHW
        image_np = np.transpose(image_np, (2, 0, 1))

        image_tensor = torch.from_numpy(image_np).float()
        mask_tensor = torch.from_numpy(mask_np).float().unsqueeze(0)  # 1,H,W

        return image_tensor, mask_tensor


# ============================================================
# 4. U-Net 模型
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

        self.up4 = nn.ConvTranspose2d(base_channels * 16, base_channels * 8, kernel_size=2, stride=2)
        self.dec4 = DoubleConv(base_channels * 16, base_channels * 8)

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
# 5. Loss 和指标
# ============================================================

def dice_loss_with_logits(logits, targets, smooth=1e-6):
    """
    logits: B,1,H,W
    targets: B,1,H,W
    """
    probs = torch.sigmoid(logits)

    probs = probs.view(probs.size(0), -1)
    targets = targets.view(targets.size(0), -1)

    intersection = (probs * targets).sum(dim=1)
    union = probs.sum(dim=1) + targets.sum(dim=1)

    dice = (2.0 * intersection + smooth) / (union + smooth)

    return 1.0 - dice.mean()


def calculate_metrics(logits, targets, threshold=0.5, smooth=1e-6):
    """
    计算道路类 IoU、Dice、Precision、Recall、Pixel Acc
    """
    probs = torch.sigmoid(logits)
    preds = (probs >= threshold).float()

    preds_flat = preds.view(-1)
    targets_flat = targets.view(-1)

    tp = ((preds_flat == 1) & (targets_flat == 1)).sum().item()
    fp = ((preds_flat == 1) & (targets_flat == 0)).sum().item()
    fn = ((preds_flat == 0) & (targets_flat == 1)).sum().item()
    tn = ((preds_flat == 0) & (targets_flat == 0)).sum().item()

    iou = (tp + smooth) / (tp + fp + fn + smooth)
    dice = (2 * tp + smooth) / (2 * tp + fp + fn + smooth)
    precision = (tp + smooth) / (tp + fp + smooth)
    recall = (tp + smooth) / (tp + fn + smooth)
    pixel_acc = (tp + tn + smooth) / (tp + tn + fp + fn + smooth)

    return {
        "iou": iou,
        "dice": dice,
        "precision": precision,
        "recall": recall,
        "pixel_acc": pixel_acc,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


# ============================================================
# 6. 训练一个 epoch
# ============================================================

def train_one_epoch(model, loader, optimizer, bce_loss_fn):
    model.train()

    total_loss = 0.0
    total_bce = 0.0
    total_dice = 0.0

    for batch_idx, (images, masks) in enumerate(loader, start=1):
        images = images.to(DEVICE)
        masks = masks.to(DEVICE)

        logits = model(images)

        bce = bce_loss_fn(logits, masks)
        dice = dice_loss_with_logits(logits, masks)

        loss = bce + dice

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        total_bce += bce.item()
        total_dice += dice.item()

        if batch_idx % 50 == 0:
            print(
                f"  batch [{batch_idx}/{len(loader)}] "
                f"loss={loss.item():.4f}, bce={bce.item():.4f}, dice={dice.item():.4f}"
            )

    n = len(loader)

    return {
        "loss": total_loss / n,
        "bce": total_bce / n,
        "dice_loss": total_dice / n,
    }


# ============================================================
# 7. 验证
# ============================================================

def validate(model, loader, bce_loss_fn):
    model.eval()

    total_loss = 0.0
    total_bce = 0.0
    total_dice_loss = 0.0

    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_tn = 0

    with torch.no_grad():
        for images, masks in loader:
            images = images.to(DEVICE)
            masks = masks.to(DEVICE)

            logits = model(images)

            bce = bce_loss_fn(logits, masks)
            dice_l = dice_loss_with_logits(logits, masks)
            loss = bce + dice_l

            total_loss += loss.item()
            total_bce += bce.item()
            total_dice_loss += dice_l.item()

            metrics = calculate_metrics(logits, masks)

            total_tp += metrics["tp"]
            total_fp += metrics["fp"]
            total_fn += metrics["fn"]
            total_tn += metrics["tn"]

    n = len(loader)

    smooth = 1e-6

    val_iou = (total_tp + smooth) / (total_tp + total_fp + total_fn + smooth)
    val_dice = (2 * total_tp + smooth) / (2 * total_tp + total_fp + total_fn + smooth)
    val_precision = (total_tp + smooth) / (total_tp + total_fp + smooth)
    val_recall = (total_tp + smooth) / (total_tp + total_fn + smooth)
    val_pixel_acc = (total_tp + total_tn + smooth) / (
        total_tp + total_tn + total_fp + total_fn + smooth
    )

    return {
        "loss": total_loss / n,
        "bce": total_bce / n,
        "dice_loss": total_dice_loss / n,
        "iou": val_iou,
        "dice": val_dice,
        "precision": val_precision,
        "recall": val_recall,
        "pixel_acc": val_pixel_acc,
    }


# ============================================================
# 8. 保存 checkpoint
# ============================================================

def save_checkpoint(path, model, optimizer, epoch, best_val_iou):
    checkpoint = {
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "best_val_iou": best_val_iou,
        "img_size": IMG_SIZE,
        "base_channels": BASE_CHANNELS,
        "pos_weight": POS_WEIGHT,
        "task": "road_binary_segmentation",
        "class_names": {
            0: "background_other",
            1: "road",
        },
    }

    torch.save(checkpoint, path)


# ============================================================
# 9. 主函数
# ============================================================

def main():
    set_seed(SEED)

    print("=" * 80)
    print("开始训练道路二值分割模型 Road U-Net")
    print("=" * 80)
    print(f"PROJECT_ROOT = {PROJECT_ROOT}")
    print(f"TRAIN_CSV = {TRAIN_CSV}")
    print(f"VAL_CSV = {VAL_CSV}")
    print(f"IMG_SIZE = {IMG_SIZE}")
    print(f"BATCH_SIZE = {BATCH_SIZE}")
    print(f"EPOCHS = {EPOCHS}")
    print(f"LEARNING_RATE = {LEARNING_RATE}")
    print(f"POS_WEIGHT = {POS_WEIGHT}")
    print(f"DEVICE = {DEVICE}")
    print("=" * 80)

    if not TRAIN_CSV.exists():
        raise FileNotFoundError(f"找不到 TRAIN_CSV: {TRAIN_CSV}")

    if not VAL_CSV.exists():
        raise FileNotFoundError(f"找不到 VAL_CSV: {VAL_CSV}")

    train_dataset = RoadDataset(TRAIN_CSV, img_size=IMG_SIZE, is_train=True)
    val_dataset = RoadDataset(VAL_CSV, img_size=IMG_SIZE, is_train=False)

    train_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=True,
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=True,
    )

    model = ProductionRoadUNet(
        in_channels=3,
        out_channels=1,
        base_channels=BASE_CHANNELS
    ).to(DEVICE)

    pos_weight_tensor = torch.tensor([POS_WEIGHT], dtype=torch.float32).to(DEVICE)
    bce_loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight_tensor)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=LEARNING_RATE,
        weight_decay=1e-4
    )

    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="max",
        factor=0.5,
        patience=3
    )

    best_val_iou = 0.0

    with open(LOG_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "epoch",
            "train_loss",
            "train_bce",
            "train_dice_loss",
            "val_loss",
            "val_bce",
            "val_dice_loss",
            "val_iou",
            "val_dice",
            "val_precision",
            "val_recall",
            "val_pixel_acc",
            "lr",
        ])

    for epoch in range(1, EPOCHS + 1):
        print("\n" + "=" * 80)
        print(f"Epoch [{epoch}/{EPOCHS}]")
        print("=" * 80)

        train_metrics = train_one_epoch(
            model=model,
            loader=train_loader,
            optimizer=optimizer,
            bce_loss_fn=bce_loss_fn,
        )

        val_metrics = validate(
            model=model,
            loader=val_loader,
            bce_loss_fn=bce_loss_fn,
        )

        current_lr = optimizer.param_groups[0]["lr"]
        scheduler.step(val_metrics["iou"])

        print("-" * 80)
        print(
            f"Train: "
            f"loss={train_metrics['loss']:.4f}, "
            f"bce={train_metrics['bce']:.4f}, "
            f"dice_loss={train_metrics['dice_loss']:.4f}"
        )
        print(
            f"Val:   "
            f"loss={val_metrics['loss']:.4f}, "
            f"bce={val_metrics['bce']:.4f}, "
            f"dice_loss={val_metrics['dice_loss']:.4f}, "
            f"IoU={val_metrics['iou']:.4f}, "
            f"Dice={val_metrics['dice']:.4f}, "
            f"Precision={val_metrics['precision']:.4f}, "
            f"Recall={val_metrics['recall']:.4f}, "
            f"PixelAcc={val_metrics['pixel_acc']:.4f}"
        )
        print(f"LR = {current_lr:.8f}")

        with open(LOG_CSV, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                epoch,
                train_metrics["loss"],
                train_metrics["bce"],
                train_metrics["dice_loss"],
                val_metrics["loss"],
                val_metrics["bce"],
                val_metrics["dice_loss"],
                val_metrics["iou"],
                val_metrics["dice"],
                val_metrics["precision"],
                val_metrics["recall"],
                val_metrics["pixel_acc"],
                current_lr,
            ])

        # 保存 last
        save_checkpoint(
            LAST_MODEL_PATH,
            model,
            optimizer,
            epoch,
            best_val_iou,
        )

        # 保存 best
        if val_metrics["iou"] > best_val_iou:
            best_val_iou = val_metrics["iou"]

            save_checkpoint(
                BEST_MODEL_PATH,
                model,
                optimizer,
                epoch,
                best_val_iou,
            )

            print(f"保存新的最优模型: {BEST_MODEL_PATH}")
            print(f"best_val_iou = {best_val_iou:.4f}")

    print("\n" + "=" * 80)
    print("道路二值分割模型训练完成")
    print(f"最优模型: {BEST_MODEL_PATH}")
    print(f"最后模型: {LAST_MODEL_PATH}")
    print(f"训练日志: {LOG_CSV}")
    print(f"best_val_iou = {best_val_iou:.4f}")
    print("=" * 80)


if __name__ == "__main__":
    main()
