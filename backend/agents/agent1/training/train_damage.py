# -*- coding: utf-8 -*-
"""
07_train_damage_unet.py

作用：
训练灾后建筑损伤等级分割模型。

任务：
输入：灾前遥感图像 pre_image + 灾后遥感图像 post_image
输出：灾后损伤等级掩码 post_damage_mask

类别：
0 = 背景
1 = 无损建筑
2 = 轻微损伤
3 = 严重损伤
4 = 摧毁

模型：
6 通道输入 U-Net
输出 5 类 logits

损失：
加权 CrossEntropy Loss + 多类别 Dice Loss

指标：
mIoU_all：包含背景的平均 IoU
mIoU_fg：排除背景后的平均 IoU，重点关注建筑损伤区域
per-class IoU：每个类别的 IoU
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

from backend.agents.agent1.src.models import DamageUNet as ProductionDamageUNet
from backend.agents.agent1.training.config import workspace_root


# ============================================================
# 1. 路径设置
# ============================================================

PROJECT_ROOT = workspace_root()

DATA_DIR = PROJECT_ROOT / "data" / "processed"
SPLIT_DIR = DATA_DIR / "splits"

TRAIN_CSV = SPLIT_DIR / "train.csv"
VAL_CSV = SPLIT_DIR / "val.csv"

CHECKPOINT_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "checkpoints"
LOG_DIR = PROJECT_ROOT / "agent1_visual_evidence" / "logs"

CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

BEST_MODEL_PATH = CHECKPOINT_DIR / "damage_unet_7ch_best.pth"
LAST_MODEL_PATH = CHECKPOINT_DIR / "damage_unet_7ch_last.pth"
LOG_PATH = LOG_DIR / "damage_unet_7ch_train_log.txt"


# ============================================================
# 2. 训练参数
# ============================================================

IMG_SIZE = 512

# 第一次先小样本跑通
MAX_TRAIN_SAMPLES = 10000
MAX_VAL_SAMPLES = 2000

EPOCHS = 20
BATCH_SIZE = 1
LEARNING_RATE = 5e-4

NUM_WORKERS = 0

NUM_CLASSES = 5

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
# 5. 类别权重
# ============================================================
# 你的数据里背景约 95%，损伤类像素极少。
# 所以背景权重要低，损伤类别权重要高。
# 这是第一版保守权重，后面可以根据效果继续调。

CLASS_WEIGHTS = torch.tensor(
    [0.02, 0.5, 10.0, 20.0, 35.0],
    dtype=torch.float32
)


DAMAGE_NAMES = {
    0: "background",
    1: "no_damage",
    2: "minor_damage",
    3: "major_damage",
    4: "destroyed",
}


# ============================================================
# 6. 读取 csv
# ============================================================

def read_csv_records(csv_path, max_samples=None, damage_focus=False):
    records = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    random.shuffle(records)

    if damage_focus:
        damaged_records = []
        normal_records = []

        for row in records:
            mask_path = DATA_DIR / row["post_damage_mask"]

            try:
                mask = Image.open(mask_path).convert("L")
                arr = np.array(mask)

                has_damage = np.any((arr == 2) | (arr == 3) | (arr == 4))

                if has_damage:
                    damaged_records.append(row)
                else:
                    normal_records.append(row)

            except Exception:
                normal_records.append(row)

        random.shuffle(damaged_records)
        random.shuffle(normal_records)

        if max_samples is not None:
            # 70% 选有损伤样本，30% 选普通样本，防止模型完全忘记无损和背景
            n_damage = int(max_samples * 0.7)
            n_normal = max_samples - n_damage

            records = damaged_records[:n_damage] + normal_records[:n_normal]
            random.shuffle(records)
        else:
            records = damaged_records + normal_records
    else:
        if max_samples is not None:
            records = records[:max_samples]

    return records


# ============================================================
# 7. 数据集定义
# ============================================================

class DamageSegDataset(Dataset):
    """
    7 通道建筑约束损伤等级分割数据集。

    输入：
    pre_image RGB        3 通道
    post_image RGB       3 通道
    pre_building_mask    1 通道

    拼接后：
    7 通道输入

    标签：
    post_damage_mask，类别值 0,1,2,3,4
    """

    def __init__(self, records, data_dir, img_size=512):
        self.records = records
        self.data_dir = data_dir
        self.img_size = img_size

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        row = self.records[idx]

        pre_path = self.data_dir / row["pre_image"]
        post_path = self.data_dir / row["post_image"]
        building_mask_path = self.data_dir / row["pre_building_mask"]
        damage_mask_path = self.data_dir / row["post_damage_mask"]

        # ---------- 读取灾前图 ----------
        pre_img = Image.open(pre_path).convert("RGB")
        pre_img = pre_img.resize((self.img_size, self.img_size), RESAMPLE_BILINEAR)
        pre_arr = np.array(pre_img).astype(np.float32) / 255.0

        # ---------- 读取灾后图 ----------
        post_img = Image.open(post_path).convert("RGB")
        post_img = post_img.resize((self.img_size, self.img_size), RESAMPLE_BILINEAR)
        post_arr = np.array(post_img).astype(np.float32) / 255.0

        # ---------- 读取灾前建筑物二值 mask ----------
        # 原始值为 0 / 255，训练时转为 0 / 1
        building_mask = Image.open(building_mask_path).convert("L")
        building_mask = building_mask.resize((self.img_size, self.img_size), RESAMPLE_NEAREST)
        building_arr = np.array(building_mask).astype(np.float32)

        building_arr = (building_arr > 0).astype(np.float32)

        # H,W -> H,W,1
        building_arr = np.expand_dims(building_arr, axis=2)

        # ---------- 拼接成 7 通道 ----------
        # pre:  H,W,3
        # post: H,W,3
        # mask: H,W,1
        # input: H,W,7
        img_arr = np.concatenate([pre_arr, post_arr, building_arr], axis=2)

        # H,W,7 -> 7,H,W
        img_arr = np.transpose(img_arr, (2, 0, 1))

        # ---------- 读取灾后损伤等级 mask ----------
        damage_mask = Image.open(damage_mask_path).convert("L")
        damage_mask = damage_mask.resize((self.img_size, self.img_size), RESAMPLE_NEAREST)
        damage_arr = np.array(damage_mask).astype(np.int64)

        # 防止异常值
        damage_arr[damage_arr < 0] = 0
        damage_arr[damage_arr > 4] = 0

        # 可选：强制建筑 mask 外部为背景
        # 这一步更符合“只在建筑区域内判断损伤”的逻辑
        building_binary = building_arr[:, :, 0]
        damage_arr[building_binary == 0] = 0

        image_tensor = torch.from_numpy(img_arr)
        mask_tensor = torch.from_numpy(damage_arr)

        return image_tensor, mask_tensor

# ============================================================
# 8. U-Net 模型
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


class DamageUNet(nn.Module):
    """
    7 通道输入 U-Net
    输入：pre RGB + post RGB = 6 通道
    输出：5 类 damage logits
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

        out = self.out_conv(d1)

        return out


# ============================================================
# 9. Loss 和指标
# ============================================================

def multiclass_dice_loss(logits, targets, num_classes=5, smooth=1.0):
    """
    多类别 Dice Loss。
    logits: B,C,H,W
    targets: B,H,W
    """
    probs = torch.softmax(logits, dim=1)

    targets_onehot = torch.zeros_like(probs)
    targets_onehot.scatter_(1, targets.unsqueeze(1), 1)

    dims = (0, 2, 3)

    intersection = torch.sum(probs * targets_onehot, dims)
    cardinality = torch.sum(probs + targets_onehot, dims)

    dice = (2.0 * intersection + smooth) / (cardinality + smooth)

    # 背景类太多，这里只计算 1~4 类的 Dice Loss
    dice_fg = dice[1:]

    return 1.0 - dice_fg.mean()


def combined_loss(logits, targets, ce_loss_fn):
    """
    加权 CrossEntropy + 多类别 Dice Loss
    """
    ce = ce_loss_fn(logits, targets)
    dice = multiclass_dice_loss(logits, targets, num_classes=NUM_CLASSES)

    return ce + dice


@torch.no_grad()
def calculate_iou_per_class(logits, targets, num_classes=5):
    """
    计算每个类别 IoU。
    logits: B,C,H,W
    targets: B,H,W
    """
    preds = torch.argmax(logits, dim=1)

    ious = []

    for cls_id in range(num_classes):
        pred_cls = preds == cls_id
        target_cls = targets == cls_id

        intersection = torch.logical_and(pred_cls, target_cls).sum().item()
        union = torch.logical_or(pred_cls, target_cls).sum().item()

        if union == 0:
            iou = np.nan
        else:
            iou = (intersection + 1.0) / (union + 1.0)

        ious.append(iou)

    return ious


def mean_ignore_nan(values):
    valid = [v for v in values if not np.isnan(v)]
    if len(valid) == 0:
        return 0.0
    return float(np.mean(valid))


# ============================================================
# 10. 训练一个 epoch
# ============================================================

def train_one_epoch(model, loader, optimizer, ce_loss_fn):
    model.train()

    total_loss = 0.0
    total_miou_all = 0.0
    total_miou_fg = 0.0
    total_batches = 0

    for images, masks in loader:
        images = images.to(DEVICE)
        masks = masks.to(DEVICE)

        optimizer.zero_grad()

        logits = model(images)
        loss = combined_loss(logits, masks, ce_loss_fn)

        loss.backward()
        optimizer.step()

        ious = calculate_iou_per_class(logits, masks, NUM_CLASSES)
        miou_all = mean_ignore_nan(ious)
        miou_fg = mean_ignore_nan(ious[1:])

        total_loss += loss.item()
        total_miou_all += miou_all
        total_miou_fg += miou_fg
        total_batches += 1

    avg_loss = total_loss / total_batches
    avg_miou_all = total_miou_all / total_batches
    avg_miou_fg = total_miou_fg / total_batches

    return avg_loss, avg_miou_all, avg_miou_fg


# ============================================================
# 11. 验证一个 epoch
# ============================================================

@torch.no_grad()
def validate_one_epoch(model, loader, ce_loss_fn):
    model.eval()

    total_loss = 0.0
    total_miou_all = 0.0
    total_miou_fg = 0.0
    total_batches = 0

    class_iou_sum = np.zeros(NUM_CLASSES, dtype=np.float64)
    class_iou_count = np.zeros(NUM_CLASSES, dtype=np.float64)

    for images, masks in loader:
        images = images.to(DEVICE)
        masks = masks.to(DEVICE)

        logits = model(images)
        loss = combined_loss(logits, masks, ce_loss_fn)

        ious = calculate_iou_per_class(logits, masks, NUM_CLASSES)

        miou_all = mean_ignore_nan(ious)
        miou_fg = mean_ignore_nan(ious[1:])

        total_loss += loss.item()
        total_miou_all += miou_all
        total_miou_fg += miou_fg
        total_batches += 1

        for cls_id, iou in enumerate(ious):
            if not np.isnan(iou):
                class_iou_sum[cls_id] += iou
                class_iou_count[cls_id] += 1

    avg_loss = total_loss / total_batches
    avg_miou_all = total_miou_all / total_batches
    avg_miou_fg = total_miou_fg / total_batches

    avg_class_iou = []

    for cls_id in range(NUM_CLASSES):
        if class_iou_count[cls_id] > 0:
            avg_class_iou.append(class_iou_sum[cls_id] / class_iou_count[cls_id])
        else:
            avg_class_iou.append(np.nan)

    return avg_loss, avg_miou_all, avg_miou_fg, avg_class_iou


# ============================================================
# 12. 主训练流程
# ============================================================

def main():
    print("=" * 70)
    print("灾后建筑损伤等级分割模型训练开始")
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
    print(f"CLASS_WEIGHTS = {CLASS_WEIGHTS.tolist()}")
    print("=" * 70)

    train_records = read_csv_records(TRAIN_CSV, max_samples=MAX_TRAIN_SAMPLES, damage_focus=True)
    val_records = read_csv_records(VAL_CSV, max_samples=MAX_VAL_SAMPLES, damage_focus=False)

    print(f"实际训练样本数：{len(train_records)}")
    print(f"实际验证样本数：{len(val_records)}")

    train_dataset = DamageSegDataset(train_records, DATA_DIR, img_size=IMG_SIZE)
    val_dataset = DamageSegDataset(val_records, DATA_DIR, img_size=IMG_SIZE)

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

    model = ProductionDamageUNet(
        in_channels=7,
        num_classes=NUM_CLASSES,
        base_channels=32,
    )
    model = model.to(DEVICE)

    class_weights = CLASS_WEIGHTS.to(DEVICE)
    ce_loss_fn = nn.CrossEntropyLoss(weight=class_weights)

    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

    best_val_miou_fg = -1.0

    with open(LOG_PATH, "w", encoding="utf-8") as log_file:
        log_file.write(
            "epoch,train_loss,train_miou_all,train_miou_fg,"
            "val_loss,val_miou_all,val_miou_fg,"
            "val_iou_background,val_iou_no_damage,val_iou_minor_damage,"
            "val_iou_major_damage,val_iou_destroyed,time_sec\n"
        )

    for epoch in range(1, EPOCHS + 1):
        start_time = time.time()

        train_loss, train_miou_all, train_miou_fg = train_one_epoch(
            model, train_loader, optimizer, ce_loss_fn
        )

        val_loss, val_miou_all, val_miou_fg, val_class_iou = validate_one_epoch(
            model, val_loader, ce_loss_fn
        )

        elapsed = time.time() - start_time

        line = (
            f"Epoch [{epoch}/{EPOCHS}] "
            f"train_loss={train_loss:.4f}, train_mIoU_all={train_miou_all:.4f}, "
            f"train_mIoU_fg={train_miou_fg:.4f} | "
            f"val_loss={val_loss:.4f}, val_mIoU_all={val_miou_all:.4f}, "
            f"val_mIoU_fg={val_miou_fg:.4f} | "
            f"class_iou=[bg={val_class_iou[0]:.4f}, no={val_class_iou[1]:.4f}, "
            f"minor={val_class_iou[2]:.4f}, major={val_class_iou[3]:.4f}, "
            f"destroyed={val_class_iou[4]:.4f}] | "
            f"time={elapsed:.1f}s"
        )

        print(line)

        with open(LOG_PATH, "a", encoding="utf-8") as log_file:
            log_file.write(
                f"{epoch},{train_loss:.6f},{train_miou_all:.6f},{train_miou_fg:.6f},"
                f"{val_loss:.6f},{val_miou_all:.6f},{val_miou_fg:.6f},"
                f"{val_class_iou[0]:.6f},{val_class_iou[1]:.6f},{val_class_iou[2]:.6f},"
                f"{val_class_iou[3]:.6f},{val_class_iou[4]:.6f},{elapsed:.2f}\n"
            )

        # 保存最后模型
        torch.save(
            {
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_miou_all": val_miou_all,
                "val_miou_fg": val_miou_fg,
                "val_class_iou": val_class_iou,
                "img_size": IMG_SIZE,
                "num_classes": NUM_CLASSES,
                "input_channels": 7,
                "class_weights": CLASS_WEIGHTS.tolist(),
            },
            LAST_MODEL_PATH,
        )

        # 按前景 mIoU 保存最佳模型
        if val_miou_fg > best_val_miou_fg:
            best_val_miou_fg = val_miou_fg

            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "val_miou_all": val_miou_all,
                    "val_miou_fg": val_miou_fg,
                    "val_class_iou": val_class_iou,
                    "img_size": IMG_SIZE,
                    "num_classes": NUM_CLASSES,
                    "input_channels": 7,
                    "class_weights": CLASS_WEIGHTS.tolist(),
                },
                BEST_MODEL_PATH,
            )

            print(f"  已保存最佳模型：{BEST_MODEL_PATH}, best_val_mIoU_fg={best_val_miou_fg:.4f}")

    print("=" * 70)
    print("训练完成")
    print(f"最佳模型：{BEST_MODEL_PATH}")
    print(f"最后模型：{LAST_MODEL_PATH}")
    print(f"训练日志：{LOG_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
