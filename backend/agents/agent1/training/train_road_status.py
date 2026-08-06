# -*- coding: utf-8 -*-
"""
26_train_spacenet8_road_status_attresunet_7ch.py

作用：
训练 SpaceNet8 道路状态识别模型。

输入：
7 通道：
1-3  : pre RGB
4-6  : post RGB
7    : road prior，道路先验 mask

输出：
3 类道路状态 mask：
0 = background / 非道路
1 = road_intact / 完好道路
2 = road_flooded / 受洪水影响道路

模型：
Attention ResUNet + SE + ASPP

数据来源：
data/SpaceNet8/processed_road_status/
"""

import os
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torch.cuda.amp import autocast, GradScaler

from backend.agents.agent1.src.models import (
    AttentionResUNet7ch as ProductionAttentionResUNet7ch,
)
from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

PROJECT_ROOT = workspace_root()

DATA_ROOT = PROJECT_ROOT / "data" / "SpaceNet8" / "processed_road_status"

PRE_DIR = DATA_ROOT / "images_pre"
POST_DIR = DATA_ROOT / "images_post"
MASK_DIR = DATA_ROOT / "masks_status"
SPLITS_DIR = DATA_ROOT / "splits"

CHECKPOINT_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "outputs" / "road_status_attresunet7ch_train"
VIS_DIR = OUTPUT_DIR / "val_visual"
LOG_DIR = OUTPUT_DIR / "logs"

for p in [OUTPUT_DIR, VIS_DIR, LOG_DIR]:
    p.mkdir(parents=True, exist_ok=True)


BEST_MODEL_PATH = CHECKPOINT_DIR / "road_status_attresunet7ch_best.pth"
LATEST_MODEL_PATH = CHECKPOINT_DIR / "road_status_attresunet7ch_latest.pth"
LOG_PATH = LOG_DIR / "train_log.jsonl"


# ============================================================
# 2. 训练参数
# ============================================================

IMG_SIZE = 512
NUM_CLASSES = 3
IN_CHANNELS = 7

BATCH_SIZE = 2
NUM_EPOCHS = 60
LEARNING_RATE = 1e-4
WEIGHT_DECAY = 1e-4

BASE_CHANNELS = 32

NUM_WORKERS = 0

RANDOM_SEED = 42

USE_AMP = True

# 如果显存不够：
# 1. BATCH_SIZE 改成 1
# 2. BASE_CHANNELS 改成 24 或 16

SAVE_VIS_EVERY_EPOCH = True


# ============================================================
# 3. 固定随机种子
# ============================================================

def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


set_seed(RANDOM_SEED)


# ============================================================
# 4. 颜色设置
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


# ============================================================
# 5. 数据集
# ============================================================

def read_split(split_name):
    split_path = SPLITS_DIR / f"{split_name}.txt"

    ids = []

    with open(split_path, "r", encoding="utf-8") as f:
        for line in f:
            sid = line.strip()
            if sid:
                ids.append(sid)

    return ids


def apply_color_jitter(img):
    """
    对 pre/post 图像做轻微颜色扰动，提高对光照、云雾、反光的鲁棒性。
    """
    if random.random() < 0.5:
        factor = random.uniform(0.85, 1.15)
        img = ImageEnhance.Brightness(img).enhance(factor)

    if random.random() < 0.5:
        factor = random.uniform(0.85, 1.15)
        img = ImageEnhance.Contrast(img).enhance(factor)

    if random.random() < 0.4:
        factor = random.uniform(0.85, 1.15)
        img = ImageEnhance.Color(img).enhance(factor)

    return img


def random_geometric_aug(pre, post, mask):
    """
    pre/post/mask 同步几何增强。
    """
    pre_np = np.array(pre)
    post_np = np.array(post)
    mask_np = np.array(mask)

    if random.random() < 0.5:
        pre_np = np.flip(pre_np, axis=1)
        post_np = np.flip(post_np, axis=1)
        mask_np = np.flip(mask_np, axis=1)

    if random.random() < 0.5:
        pre_np = np.flip(pre_np, axis=0)
        post_np = np.flip(post_np, axis=0)
        mask_np = np.flip(mask_np, axis=0)

    k = random.randint(0, 3)

    if k > 0:
        pre_np = np.rot90(pre_np, k)
        post_np = np.rot90(post_np, k)
        mask_np = np.rot90(mask_np, k)

    pre_np = pre_np.copy()
    post_np = post_np.copy()
    mask_np = mask_np.copy()

    return pre_np, post_np, mask_np


def make_road_prior(mask_np, is_train=True):
    """
    从标签生成 road prior：
    road prior = mask > 0

    训练时做轻微扰动，模拟 EBD 阶段 road_unet 预测不完美的情况。
    """
    prior = (mask_np > 0).astype(np.uint8)

    if not is_train:
        return prior.astype(np.float32)

    prior_img = Image.fromarray((prior * 255).astype(np.uint8))

    # 随机膨胀 / 腐蚀，让模型不要过度依赖完美道路先验
    r = random.random()

    if r < 0.20:
        prior_img = prior_img.filter(ImageFilter.MaxFilter(3))
    elif r < 0.40:
        prior_img = prior_img.filter(ImageFilter.MinFilter(3))

    prior = (np.array(prior_img) > 127).astype(np.uint8)

    # 随机丢失少量道路像素
    if random.random() < 0.35:
        keep = (np.random.rand(*prior.shape) > random.uniform(0.02, 0.08)).astype(np.uint8)
        prior = prior * keep

    return prior.astype(np.float32)


class RoadStatusDataset(Dataset):
    def __init__(self, split_name, is_train):
        self.split_name = split_name
        self.is_train = is_train
        self.ids = read_split(split_name)

    def __len__(self):
        return len(self.ids)

    def __getitem__(self, idx):
        sample_id = self.ids[idx]

        pre_path = PRE_DIR / f"{sample_id}_pre.png"
        post_path = POST_DIR / f"{sample_id}_post.png"
        mask_path = MASK_DIR / f"{sample_id}_road_status_mask.png"

        pre = Image.open(pre_path).convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
        post = Image.open(post_path).convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
        mask = Image.open(mask_path).convert("L").resize((IMG_SIZE, IMG_SIZE), Image.NEAREST)

        if self.is_train:
            pre = apply_color_jitter(pre)
            post = apply_color_jitter(post)

            pre_np, post_np, mask_np = random_geometric_aug(pre, post, mask)
        else:
            pre_np = np.array(pre)
            post_np = np.array(post)
            mask_np = np.array(mask)

        mask_np = mask_np.astype(np.uint8)
        mask_np[mask_np > 2] = 0

        road_prior = make_road_prior(mask_np, is_train=self.is_train)

        pre_tensor = torch.from_numpy(pre_np.transpose(2, 0, 1)).float() / 255.0
        post_tensor = torch.from_numpy(post_np.transpose(2, 0, 1)).float() / 255.0
        prior_tensor = torch.from_numpy(road_prior[None, :, :]).float()

        # RGB 归一化到 [-1, 1]，road prior 保持 0/1
        pre_tensor = (pre_tensor - 0.5) / 0.5
        post_tensor = (post_tensor - 0.5) / 0.5

        x = torch.cat([pre_tensor, post_tensor, prior_tensor], dim=0)
        y = torch.from_numpy(mask_np).long()

        return x, y, sample_id


# ============================================================
# 6. 模型：Attention ResUNet + SE + ASPP
# ============================================================

class SEBlock(nn.Module):
    def __init__(self, channels, reduction=16):
        super().__init__()

        hidden = max(channels // reduction, 8)

        self.fc = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, hidden, kernel_size=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(hidden, channels, kernel_size=1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        weight = self.fc(x)
        return x * weight


class ResBlock(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()

        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_channels)

        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)

        self.se = SEBlock(out_channels)

        if in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
                nn.BatchNorm2d(out_channels),
            )
        else:
            self.shortcut = nn.Identity()

        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        identity = self.shortcut(x)

        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out = self.se(out)

        out = out + identity
        out = self.relu(out)

        return out


class ASPP(nn.Module):
    """
    多尺度空洞卷积，用于增强道路长距离上下文。
    """
    def __init__(self, in_channels, out_channels):
        super().__init__()

        self.branch1 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

        self.branch2 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=2, dilation=2, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

        self.branch3 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=4, dilation=4, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

        self.branch4 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=6, dilation=6, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

        self.project = nn.Sequential(
            nn.Conv2d(out_channels * 4, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        b1 = self.branch1(x)
        b2 = self.branch2(x)
        b3 = self.branch3(x)
        b4 = self.branch4(x)

        out = torch.cat([b1, b2, b3, b4], dim=1)
        out = self.project(out)

        return out


class AttentionGate(nn.Module):
    def __init__(self, gate_channels, skip_channels, inter_channels):
        super().__init__()

        self.gate_conv = nn.Sequential(
            nn.Conv2d(gate_channels, inter_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(inter_channels),
        )

        self.skip_conv = nn.Sequential(
            nn.Conv2d(skip_channels, inter_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(inter_channels),
        )

        self.psi = nn.Sequential(
            nn.Conv2d(inter_channels, 1, kernel_size=1, bias=True),
            nn.Sigmoid(),
        )

        self.relu = nn.ReLU(inplace=True)

    def forward(self, gate, skip):
        g = self.gate_conv(gate)
        s = self.skip_conv(skip)

        if g.shape[-2:] != s.shape[-2:]:
            g = F.interpolate(g, size=s.shape[-2:], mode="bilinear", align_corners=False)

        att = self.relu(g + s)
        att = self.psi(att)

        return skip * att


class UpBlock(nn.Module):
    def __init__(self, in_channels, skip_channels, out_channels):
        super().__init__()

        self.up = nn.ConvTranspose2d(in_channels, out_channels, kernel_size=2, stride=2)

        self.att = AttentionGate(
            gate_channels=out_channels,
            skip_channels=skip_channels,
            inter_channels=max(out_channels // 2, 16),
        )

        self.conv = ResBlock(out_channels + skip_channels, out_channels)

    def forward(self, x, skip):
        x = self.up(x)

        if x.shape[-2:] != skip.shape[-2:]:
            x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)

        skip = self.att(x, skip)

        x = torch.cat([x, skip], dim=1)
        x = self.conv(x)

        return x


class AttentionResUNet7ch(nn.Module):
    def __init__(self, in_channels=7, num_classes=3, base_channels=32):
        super().__init__()

        b = base_channels

        self.enc1 = ResBlock(in_channels, b)
        self.pool1 = nn.MaxPool2d(2)

        self.enc2 = ResBlock(b, b * 2)
        self.pool2 = nn.MaxPool2d(2)

        self.enc3 = ResBlock(b * 2, b * 4)
        self.pool3 = nn.MaxPool2d(2)

        self.enc4 = ResBlock(b * 4, b * 8)
        self.pool4 = nn.MaxPool2d(2)

        self.bottleneck = nn.Sequential(
            ResBlock(b * 8, b * 16),
            ASPP(b * 16, b * 16),
        )

        self.dec4 = UpBlock(b * 16, b * 8, b * 8)
        self.dec3 = UpBlock(b * 8, b * 4, b * 4)
        self.dec2 = UpBlock(b * 4, b * 2, b * 2)
        self.dec1 = UpBlock(b * 2, b, b)

        self.out_conv = nn.Conv2d(b, num_classes, kernel_size=1)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool1(e1))
        e3 = self.enc3(self.pool2(e2))
        e4 = self.enc4(self.pool3(e3))

        b = self.bottleneck(self.pool4(e4))

        d4 = self.dec4(b, e4)
        d3 = self.dec3(d4, e3)
        d2 = self.dec2(d3, e2)
        d1 = self.dec1(d2, e1)

        out = self.out_conv(d1)

        return out


# ============================================================
# 7. Loss
# ============================================================

def compute_class_weights(train_ids):
    counts = np.zeros(NUM_CLASSES, dtype=np.float64)

    for sid in train_ids:
        mask_path = MASK_DIR / f"{sid}_road_status_mask.png"
        mask = np.array(Image.open(mask_path).convert("L"))

        mask[mask > 2] = 0

        for c in range(NUM_CLASSES):
            counts[c] += np.sum(mask == c)

    freq = counts / max(counts.sum(), 1.0)

    weights = 1.0 / np.log(1.02 + freq)
    weights = weights / weights.mean()
    weights = np.clip(weights, 0.2, 8.0)

    print("class pixel counts:", counts)
    print("class freq:", freq)
    print("class weights:", weights)

    return torch.tensor(weights, dtype=torch.float32)


class RoadStatusLoss(nn.Module):
    def __init__(self, class_weights):
        super().__init__()

        self.register_buffer("class_weights", class_weights.float())

    def dice_loss_road_classes(self, logits, target, eps=1e-6):
        probs = torch.softmax(logits, dim=1)

        dice_losses = []

        # 只对道路类算 Dice，避免背景过大主导训练
        for cls in [1, 2]:
            pred = probs[:, cls, :, :]
            gt = (target == cls).float()

            inter = (pred * gt).sum(dim=(1, 2))
            union = pred.sum(dim=(1, 2)) + gt.sum(dim=(1, 2))

            dice = (2 * inter + eps) / (union + eps)
            dice_losses.append(1 - dice.mean())

        return sum(dice_losses) / len(dice_losses)

    def forward(self, logits, target):
        ce = F.cross_entropy(
            logits,
            target,
            weight=self.class_weights,
        )

        dice = self.dice_loss_road_classes(logits, target)

        loss = 0.45 * ce + 0.55 * dice

        return loss


# ============================================================
# 8. 指标
# ============================================================

def fast_confusion_matrix(pred, target, num_classes):
    pred = pred.view(-1)
    target = target.view(-1)

    valid = (target >= 0) & (target < num_classes)

    hist = torch.bincount(
        num_classes * target[valid] + pred[valid],
        minlength=num_classes ** 2,
    ).reshape(num_classes, num_classes)

    return hist


def metrics_from_confmat(confmat):
    confmat = confmat.float()

    metrics = {}

    ious = []
    dices = []

    for cls in range(NUM_CLASSES):
        tp = confmat[cls, cls]
        fp = confmat[:, cls].sum() - tp
        fn = confmat[cls, :].sum() - tp

        iou = tp / (tp + fp + fn + 1e-6)
        dice = (2 * tp) / (2 * tp + fp + fn + 1e-6)

        metrics[f"iou_{cls}"] = float(iou.item())
        metrics[f"dice_{cls}"] = float(dice.item())

        ious.append(iou)
        dices.append(dice)

    # 道路类平均，不包含背景
    metrics["miou_road"] = float(((ious[1] + ious[2]) / 2).item())
    metrics["mdice_road"] = float(((dices[1] + dices[2]) / 2).item())

    # flooded 类 precision / recall
    cls = 2
    tp = confmat[cls, cls]
    fp = confmat[:, cls].sum() - tp
    fn = confmat[cls, :].sum() - tp

    precision = tp / (tp + fp + 1e-6)
    recall = tp / (tp + fn + 1e-6)

    metrics["flooded_precision"] = float(precision.item())
    metrics["flooded_recall"] = float(recall.item())

    return metrics


# ============================================================
# 9. 可视化
# ============================================================

def denorm_rgb(x):
    """
    x: [3,H,W]，范围 [-1,1]
    """
    arr = x.detach().cpu().numpy()
    arr = (arr * 0.5 + 0.5) * 255.0
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    arr = arr.transpose(1, 2, 0)
    return arr


def save_val_visual(model, val_loader, device, epoch):
    model.eval()

    try:
        x, y, sample_ids = next(iter(val_loader))
    except StopIteration:
        return

    x = x.to(device)
    y = y.to(device)

    with torch.no_grad():
        logits = model(x)
        pred = torch.argmax(logits, dim=1)

    x0 = x[0].detach().cpu()
    gt0 = y[0].detach().cpu().numpy().astype(np.uint8)
    pred0 = pred[0].detach().cpu().numpy().astype(np.uint8)

    pre_rgb = denorm_rgb(x0[0:3])
    post_rgb = denorm_rgb(x0[3:6])

    prior = x0[6].numpy()
    prior_rgb = np.zeros_like(pre_rgb)
    prior_rgb[prior > 0.5] = (255, 255, 255)

    gt_color = mask_to_color(gt0)
    pred_color = mask_to_color(pred0)

    pred_overlay = overlay_on_image(post_rgb, pred0)

    w, h = IMG_SIZE, IMG_SIZE
    canvas = Image.new("RGB", (w * 3, h * 2), (0, 0, 0))

    images = [
        (pre_rgb, "Pre image"),
        (post_rgb, "Post image"),
        (prior_rgb, "Road prior"),
        (gt_color, "GT road status"),
        (pred_color, "Pred road status"),
        (pred_overlay, "Pred overlay"),
    ]

    draw = ImageDraw.Draw(canvas)

    for i, (img, title) in enumerate(images):
        row = i // 3
        col = i % 3

        x0_pos = col * w
        y0_pos = row * h

        canvas.paste(Image.fromarray(img), (x0_pos, y0_pos))
        draw.text((x0_pos + 10, y0_pos + 10), title, fill=(255, 255, 255))

    save_path = VIS_DIR / f"epoch_{epoch:03d}_{sample_ids[0]}_val.png"
    canvas.save(save_path)


# ============================================================
# 10. 训练与验证
# ============================================================

def train_one_epoch(model, loader, criterion, optimizer, scaler, device):
    model.train()

    total_loss = 0.0
    confmat = torch.zeros(NUM_CLASSES, NUM_CLASSES, dtype=torch.long, device=device)

    for x, y, _ in loader:
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)

        with autocast(enabled=USE_AMP):
            logits = model(x)
            loss = criterion(logits, y)

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

        total_loss += loss.item() * x.size(0)

        with torch.no_grad():
            pred = torch.argmax(logits, dim=1)
            confmat += fast_confusion_matrix(pred, y, NUM_CLASSES).to(device)

    avg_loss = total_loss / len(loader.dataset)
    metrics = metrics_from_confmat(confmat.detach().cpu())

    return avg_loss, metrics


def validate(model, loader, criterion, device):
    model.eval()

    total_loss = 0.0
    confmat = torch.zeros(NUM_CLASSES, NUM_CLASSES, dtype=torch.long, device=device)

    with torch.no_grad():
        for x, y, _ in loader:
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)

            logits = model(x)
            loss = criterion(logits, y)

            total_loss += loss.item() * x.size(0)

            pred = torch.argmax(logits, dim=1)
            confmat += fast_confusion_matrix(pred, y, NUM_CLASSES).to(device)

    avg_loss = total_loss / len(loader.dataset)
    metrics = metrics_from_confmat(confmat.detach().cpu())

    return avg_loss, metrics


def save_checkpoint(path, model, optimizer, epoch, best_score, config):
    ckpt = {
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "best_score": best_score,
        "config": config,
        "class_names": CLASS_NAMES,
        "class_colors": CLASS_COLORS,
    }

    torch.save(ckpt, path)


# ============================================================
# 11. 主函数
# ============================================================

def main():
    print("=" * 100)
    print("SpaceNet8 7通道道路状态模型训练")
    print("=" * 100)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("device =", device)

    train_ids = read_split("train")
    val_ids = read_split("val")
    test_ids = read_split("test")

    print(f"train: {len(train_ids)}")
    print(f"val  : {len(val_ids)}")
    print(f"test : {len(test_ids)}")

    class_weights = compute_class_weights(train_ids)

    train_dataset = RoadStatusDataset("train", is_train=True)
    val_dataset = RoadStatusDataset("val", is_train=False)

    train_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=True,
        drop_last=False,
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=True,
        drop_last=False,
    )

    model = ProductionAttentionResUNet7ch(
        in_channels=IN_CHANNELS,
        num_classes=NUM_CLASSES,
        base_channels=BASE_CHANNELS,
    ).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    print(f"model params: {total_params / 1e6:.2f} M")
    print(f"trainable params: {trainable_params / 1e6:.2f} M")

    criterion = RoadStatusLoss(class_weights=class_weights).to(device)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
    )

    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=NUM_EPOCHS,
        eta_min=1e-6,
    )

    scaler = GradScaler(enabled=USE_AMP)

    config = {
        "img_size": IMG_SIZE,
        "num_classes": NUM_CLASSES,
        "in_channels": IN_CHANNELS,
        "batch_size": BATCH_SIZE,
        "num_epochs": NUM_EPOCHS,
        "learning_rate": LEARNING_RATE,
        "weight_decay": WEIGHT_DECAY,
        "base_channels": BASE_CHANNELS,
        "model": "AttentionResUNet7ch_SE_ASPP",
        "loss": "0.45 weighted CE + 0.55 road-class Dice",
        "class_weights": class_weights.tolist(),
    }

    best_score = -1.0

    if LOG_PATH.exists():
        LOG_PATH.unlink()

    for epoch in range(1, NUM_EPOCHS + 1):
        print("=" * 100)
        print(f"Epoch [{epoch}/{NUM_EPOCHS}]")

        train_loss, train_metrics = train_one_epoch(
            model=model,
            loader=train_loader,
            criterion=criterion,
            optimizer=optimizer,
            scaler=scaler,
            device=device,
        )

        val_loss, val_metrics = validate(
            model=model,
            loader=val_loader,
            criterion=criterion,
            device=device,
        )

        scheduler.step()

        # 更重视 flooded 类
        score = 0.4 * val_metrics["iou_1"] + 0.6 * val_metrics["iou_2"]

        lr = optimizer.param_groups[0]["lr"]

        print(
            f"lr={lr:.6e} | "
            f"train_loss={train_loss:.4f} | "
            f"val_loss={val_loss:.4f}"
        )

        print(
            "Train: "
            f"miou_road={train_metrics['miou_road']:.4f}, "
            f"iou_intact={train_metrics['iou_1']:.4f}, "
            f"iou_flooded={train_metrics['iou_2']:.4f}, "
            f"flooded_P={train_metrics['flooded_precision']:.4f}, "
            f"flooded_R={train_metrics['flooded_recall']:.4f}"
        )

        print(
            "Val  : "
            f"miou_road={val_metrics['miou_road']:.4f}, "
            f"iou_intact={val_metrics['iou_1']:.4f}, "
            f"iou_flooded={val_metrics['iou_2']:.4f}, "
            f"flooded_P={val_metrics['flooded_precision']:.4f}, "
            f"flooded_R={val_metrics['flooded_recall']:.4f}, "
            f"score={score:.4f}"
        )

        log_item = {
            "epoch": epoch,
            "lr": lr,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "train_metrics": train_metrics,
            "val_metrics": val_metrics,
            "score": score,
            "best_score": best_score,
        }

        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_item, ensure_ascii=False) + "\n")

        save_checkpoint(
            path=LATEST_MODEL_PATH,
            model=model,
            optimizer=optimizer,
            epoch=epoch,
            best_score=best_score,
            config=config,
        )

        if score > best_score:
            best_score = score

            save_checkpoint(
                path=BEST_MODEL_PATH,
                model=model,
                optimizer=optimizer,
                epoch=epoch,
                best_score=best_score,
                config=config,
            )

            print(f"[保存最佳模型] best_score={best_score:.4f}")
            print(f"best model path: {BEST_MODEL_PATH}")

        if SAVE_VIS_EVERY_EPOCH:
            save_val_visual(model, val_loader, device, epoch)

    print("=" * 100)
    print("训练完成")
    print(f"best_score = {best_score:.4f}")
    print(f"best model = {BEST_MODEL_PATH}")
    print(f"latest model = {LATEST_MODEL_PATH}")
    print(f"log = {LOG_PATH}")
    print(f"val visual = {VIS_DIR}")
    print("=" * 100)


if __name__ == "__main__":
    main()
