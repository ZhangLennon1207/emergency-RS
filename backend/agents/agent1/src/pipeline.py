# -*- coding: utf-8 -*-
"""
31_agent1_pipeline.py

Agent1：时空视觉证据感知与证据账本生成智能体

输入：
    灾前图像 + 灾后图像 + sample_id

自动完成：
    1. 建筑二值分割
    2. 建筑五分类损伤预测
    3. 建筑实例化与实例级损伤统一
    4. 道路二值分割
    5. 道路受影响预测与后处理
    6. 建筑与道路融合
    7. 置信度统计
    8. 给 Agent3 输出核心证据账本和融合图
    9. 给 Agent4 输出场景摘要和人工复核信息

说明：
    - Agent2 不使用本脚本输出，只读取灾前、灾后原图。
    - Agent3 使用：
        for_agent3/evidence_ledger_core.json
        fusion/fused_color.png
        fusion/fused_overlay.png
    - Agent4 使用：
        for_agent4/agent1_report_summary.json
        for_agent4/review_flags.json

首次运行建议：
    先用一条此前已经成功处理的 EBD 样本测试。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

import torch
import torch.nn as nn
import torch.nn.functional as F

from backend.agents.agent1.src.models import (
    AttentionResUNet7ch,
    BuildingUNet,
    DamageUNet,
    RoadUNet,
)


# ============================================================
# 1. 路径配置
# ============================================================

AGENT_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_DIR = Path(
    os.environ.get("AGENT1_CHECKPOINT_DIR", AGENT_ROOT / "checkpoints")
)
DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get("AGENT1_OUTPUT_ROOT", AGENT_ROOT / "outputs" / "agent1_runs")
)

# 检查点候选名称
BUILDING_CKPT_CANDIDATES = [
    "building_unet_medium_best.pth",
    "building_unet_best.pth",
]

DAMAGE_CKPT_CANDIDATES = [
    "damage_unet_7ch_best.pth",
    "damage_unet_best.pth",
]

ROAD_BINARY_CKPT_CANDIDATES = [
    "road_unet_best.pth",
    "road_unet_medium_best.pth",
    "road_binary_unet_best.pth",
]

ROAD_STATUS_CKPT_CANDIDATES = [
    "road_status_attresunet7ch_best.pth",
]


# ============================================================
# 2. 推理参数
# ============================================================

IMAGE_SIZE = 512

BUILDING_THRESHOLD = 0.50
BUILDING_MIN_AREA = 24
BUILDING_CLOSE_KERNEL = 5

ROAD_THRESHOLD = 0.50
ROAD_MIN_AREA = 30
ROAD_CLOSE_KERNEL = 7

# 建筑实例级损伤统一规则
DESTROYED_RATIO_THRESHOLD = 0.05
MAJOR_RATIO_THRESHOLD = 0.10
MINOR_RATIO_THRESHOLD = 0.05

# 道路状态：采用当前已经验证效果较好的保守规则
ROAD_AFFECTED_PROB_THRESHOLD = 0.60
ROAD_RED_MIN_AREA = 60
ROAD_RED_CLOSE_KERNEL = 9
ROAD_RED_DILATE_ITERATIONS = 1
ROAD_RED_SECOND_CLOSE_KERNEL = 7

# 不确定性只提供给 Agent4
BUILDING_UNCERTAIN_LOW = 0.40
BUILDING_UNCERTAIN_HIGH = 0.60

ROAD_UNCERTAIN_LOW = 0.40
ROAD_UNCERTAIN_HIGH = 0.60
ROAD_UNCERTAIN_REVIEW_RATIO = 0.15
ROAD_HIGH_RATIO_REVIEW = 0.80
ROAD_AFFECTED_EXIST_RATIO = 0.05

# 融合叠加图参数
BACKGROUND_DARKEN_FACTOR = 0.55
ROAD_OVERLAY_ALPHA = 0.82
BUILDING_OVERLAY_ALPHA = 0.82


# ============================================================
# 3. 类别名称与颜色
# ============================================================

BUILDING_LEVEL_NAMES = {
    0: "background",
    1: "no_damage",
    2: "minor_damage",
    3: "major_damage",
    4: "destroyed",
}

BUILDING_LEVEL_NAMES_ZH = {
    0: "背景",
    1: "无明显损伤",
    2: "轻微损伤",
    3: "严重损伤",
    4: "摧毁",
}

BUILDING_COLORS = {
    0: (0, 0, 0),
    1: (0, 200, 0),
    2: (255, 255, 0),
    3: (255, 140, 0),
    4: (255, 0, 0),
}

ROAD_STATUS_COLORS = {
    0: (0, 0, 0),
    1: (255, 255, 255),
    2: (255, 0, 0),
}

# 融合类别：
# 0 背景；1 完好道路；2 受影响道路；
# 10~13 为建筑无损/轻微/严重/摧毁
FUSED_COLORS = {
    0: (0, 0, 0),
    1: (255, 255, 255),
    2: (255, 0, 0),
    10: (0, 200, 0),
    11: (255, 255, 0),
    12: (255, 140, 0),
    13: (255, 0, 0),
}


# ============================================================
# 4. 本地兜底 U-Net
# ============================================================

class DoubleConv(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()

        self.block = nn.Sequential(
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size=3,
                padding=1,
                bias=False,
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),

            nn.Conv2d(
                out_channels,
                out_channels,
                kernel_size=3,
                padding=1,
                bias=False,
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class LocalSimpleUNet3(nn.Module):
    """
    与当前建筑/损伤 SimpleUNet 相匹配的三层下采样 U-Net。
    仅在无法从已有脚本中导入模型类时使用。
    """

    def __init__(
        self,
        in_channels: int = 3,
        out_channels: int = 1,
        base_channels: int = 32,
        num_classes: Optional[int] = None,
    ):
        super().__init__()

        if num_classes is not None:
            out_channels = num_classes

        b = base_channels

        self.enc1 = DoubleConv(in_channels, b)
        self.pool1 = nn.MaxPool2d(2)

        self.enc2 = DoubleConv(b, b * 2)
        self.pool2 = nn.MaxPool2d(2)

        self.enc3 = DoubleConv(b * 2, b * 4)
        self.pool3 = nn.MaxPool2d(2)

        self.bottleneck = DoubleConv(b * 4, b * 8)

        self.up3 = nn.ConvTranspose2d(
            b * 8,
            b * 4,
            kernel_size=2,
            stride=2,
        )
        self.dec3 = DoubleConv(b * 8, b * 4)

        self.up2 = nn.ConvTranspose2d(
            b * 4,
            b * 2,
            kernel_size=2,
            stride=2,
        )
        self.dec2 = DoubleConv(b * 4, b * 2)

        self.up1 = nn.ConvTranspose2d(
            b * 2,
            b,
            kernel_size=2,
            stride=2,
        )
        self.dec1 = DoubleConv(b * 2, b)

        self.out_conv = nn.Conv2d(
            b,
            out_channels,
            kernel_size=1,
        )

    @staticmethod
    def resize_like(
        x: torch.Tensor,
        reference: torch.Tensor,
    ) -> torch.Tensor:
        if x.shape[-2:] != reference.shape[-2:]:
            x = F.interpolate(
                x,
                size=reference.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )

        return x

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        enc1 = self.enc1(x)
        enc2 = self.enc2(self.pool1(enc1))
        enc3 = self.enc3(self.pool2(enc2))

        bottleneck = self.bottleneck(
            self.pool3(enc3)
        )

        dec3 = self.resize_like(
            self.up3(bottleneck),
            enc3,
        )
        dec3 = self.dec3(
            torch.cat([dec3, enc3], dim=1)
        )

        dec2 = self.resize_like(
            self.up2(dec3),
            enc2,
        )
        dec2 = self.dec2(
            torch.cat([dec2, enc2], dim=1)
        )

        dec1 = self.resize_like(
            self.up1(dec2),
            enc1,
        )
        dec1 = self.dec1(
            torch.cat([dec1, enc1], dim=1)
        )

        return self.out_conv(dec1)


# ============================================================
# 5. 模型加载工具
# ============================================================

def find_checkpoint(
    candidates: Iterable[str],
    include_keywords: Iterable[str],
    exclude_keywords: Iterable[str] = (),
    checkpoint_dir: Path = CHECKPOINT_DIR,
) -> Path:
    """
    先按明确文件名寻找；
    找不到时再按关键词自动匹配。
    """
    for filename in candidates:
        path = checkpoint_dir / filename

        if path.exists():
            return path

    all_checkpoints = sorted(
        checkpoint_dir.glob("*.pth")
    )

    for path in all_checkpoints:
        name = path.name.lower()

        include_ok = all(
            keyword.lower() in name
            for keyword in include_keywords
        )

        exclude_ok = not any(
            keyword.lower() in name
            for keyword in exclude_keywords
        )

        if include_ok and exclude_ok:
            return path

    raise FileNotFoundError(
        "没有找到模型检查点。\n"
        f"检查点目录：{checkpoint_dir}\n"
        f"候选名称：{list(candidates)}"
    )


def extract_state_dict(
    checkpoint: Any,
) -> Dict[str, torch.Tensor]:
    if isinstance(checkpoint, dict):
        for key in [
            "model_state_dict",
            "state_dict",
            "model",
            "net",
            "network",
        ]:
            value = checkpoint.get(key)

            if isinstance(value, dict):
                checkpoint = value
                break

    if not isinstance(checkpoint, dict):
        raise TypeError(
            "检查点中没有可用的 state_dict。"
        )

    cleaned_state_dict = {}

    for key, value in checkpoint.items():
        if not torch.is_tensor(value):
            continue

        new_key = key

        for prefix in [
            "module.",
            "model.",
            "net.",
        ]:
            if new_key.startswith(prefix):
                new_key = new_key[len(prefix):]

        cleaned_state_dict[new_key] = value

    return cleaned_state_dict


def infer_base_channels(
    state_dict: Dict[str, torch.Tensor],
    default: int = 32,
) -> int:
    preferred_keys = [
        "enc1.block.0.weight",
        "enc1.conv.0.weight",
        "encoder1.block.0.weight",
        "down1.conv.0.weight",
        "inc.double_conv.0.weight",
    ]

    for key in preferred_keys:
        tensor = state_dict.get(key)

        if tensor is not None and tensor.ndim == 4:
            return int(tensor.shape[0])

    for tensor in state_dict.values():
        if tensor.ndim == 4:
            return int(tensor.shape[0])

    return default


def instantiate_model_flexibly(
    model_class,
    in_channels: int,
    out_channels: int,
    base_channels: int,
):
    keyword_attempts = [
        {
            "in_channels": in_channels,
            "out_channels": out_channels,
            "base_channels": base_channels,
        },
        {
            "in_channels": in_channels,
            "num_classes": out_channels,
            "base_channels": base_channels,
        },
        {
            "n_channels": in_channels,
            "n_classes": out_channels,
            "base_channels": base_channels,
        },
        {
            "in_ch": in_channels,
            "out_ch": out_channels,
            "base_ch": base_channels,
        },
        {
            "in_channels": in_channels,
            "out_channels": out_channels,
        },
        {
            "in_channels": in_channels,
            "num_classes": out_channels,
        },
    ]

    last_error = None

    for kwargs in keyword_attempts:
        try:
            return model_class(**kwargs)
        except TypeError as error:
            last_error = error

    for args in [
        (in_channels, out_channels, base_channels),
        (in_channels, out_channels),
    ]:
        try:
            return model_class(*args)
        except TypeError as error:
            last_error = error

    raise TypeError(
        f"无法实例化模型类：{model_class.__name__}\n"
        f"最后错误：{last_error}"
    )


def load_segmentation_model(
    checkpoint_path: Path,
    model_class: type[nn.Module],
    in_channels: int,
    out_channels: int,
    device: torch.device,
):
    checkpoint = torch.load(
        checkpoint_path,
        map_location=device,
        weights_only=False,
    )

    state_dict = extract_state_dict(
        checkpoint
    )

    base_channels = infer_base_channels(
        state_dict,
        default=32,
    )

    model = instantiate_model_flexibly(
        model_class=model_class,
        in_channels=in_channels,
        out_channels=out_channels,
        base_channels=base_channels,
    ).to(device)

    try:
        model.load_state_dict(state_dict, strict=True)
    except RuntimeError as error:
        raise RuntimeError(
            f"模型结构和检查点不匹配：{checkpoint_path.name}\n{error}"
        ) from error

    model.eval()

    return model, checkpoint


def load_road_status_model(
    checkpoint_path: Path,
    device: torch.device,
):
    checkpoint = torch.load(
        checkpoint_path,
        map_location=device,
        weights_only=False,
    )

    state_dict = extract_state_dict(
        checkpoint
    )

    config = (
        checkpoint.get("config", {})
        if isinstance(checkpoint, dict)
        else {}
    )

    base_channels = int(
        config.get("base_channels", 32)
    )

    in_channels = int(
        config.get("in_channels", 7)
    )

    num_classes = int(
        config.get("num_classes", 3)
    )

    model = AttentionResUNet7ch(
        in_channels=in_channels,
        num_classes=num_classes,
        base_channels=base_channels,
    ).to(device)

    model.load_state_dict(
        state_dict,
        strict=True,
    )

    model.eval()

    return model, checkpoint


# ============================================================
# 6. 图像与形态学工具
# ============================================================

def load_rgb(
    path: Path,
    size: int = IMAGE_SIZE,
) -> np.ndarray:
    image = Image.open(path).convert("RGB")

    image = image.resize(
        (size, size),
        Image.BILINEAR,
    )

    return np.array(
        image,
        dtype=np.uint8,
    )


def image_to_tensor_01(
    image_rgb: np.ndarray,
) -> torch.Tensor:
    array = (
        image_rgb.astype(np.float32)
        / 255.0
    )

    return torch.from_numpy(
        array.transpose(2, 0, 1)
    ).float()


def image_to_tensor_minus1_1(
    image_rgb: np.ndarray,
) -> torch.Tensor:
    array = (
        image_rgb.astype(np.float32)
        / 255.0
    )

    array = (
        array - 0.5
    ) / 0.5

    return torch.from_numpy(
        array.transpose(2, 0, 1)
    ).float()


def remove_small_components(
    binary: np.ndarray,
    min_area: int,
) -> np.ndarray:
    binary = (
        binary > 0
    ).astype(np.uint8)

    (
        number_of_labels,
        labels,
        statistics,
        _,
    ) = cv2.connectedComponentsWithStats(
        binary,
        connectivity=8,
    )

    output = np.zeros_like(
        binary,
        dtype=np.uint8,
    )

    for label_id in range(
        1,
        number_of_labels,
    ):
        area = int(
            statistics[
                label_id,
                cv2.CC_STAT_AREA,
            ]
        )

        if area >= min_area:
            output[
                labels == label_id
            ] = 1

    return output


def morph_close(
    binary: np.ndarray,
    kernel_size: int,
    iterations: int = 1,
) -> np.ndarray:
    binary = (
        binary > 0
    ).astype(np.uint8)

    if kernel_size <= 1:
        return binary

    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (kernel_size, kernel_size),
    )

    output = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=iterations,
    )

    return (
        output > 0
    ).astype(np.uint8)


def clean_binary_mask(
    binary: np.ndarray,
    min_area: int,
    close_kernel: int,
) -> np.ndarray:
    binary = remove_small_components(
        binary,
        max(8, min_area // 3),
    )

    binary = morph_close(
        binary,
        close_kernel,
        1,
    )

    binary = remove_small_components(
        binary,
        min_area,
    )

    return binary.astype(np.uint8)


def postprocess_road_red(
    red: np.ndarray,
    road_prior: np.ndarray,
) -> np.ndarray:
    red = (
        red > 0
    ).astype(np.uint8)

    road_prior = (
        road_prior > 0
    ).astype(np.uint8)

    red *= road_prior

    red = remove_small_components(
        red,
        max(
            8,
            ROAD_RED_MIN_AREA // 3,
        ),
    )

    red = morph_close(
        red,
        ROAD_RED_CLOSE_KERNEL,
        1,
    )

    red *= road_prior

    if ROAD_RED_DILATE_ITERATIONS > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (3, 3),
        )

        red = cv2.dilate(
            red,
            kernel,
            iterations=(
                ROAD_RED_DILATE_ITERATIONS
            ),
        )

        red = (
            red > 0
        ).astype(np.uint8)

        red *= road_prior

    red = morph_close(
        red,
        ROAD_RED_SECOND_CLOSE_KERNEL,
        1,
    )

    red *= road_prior

    red = remove_small_components(
        red,
        ROAD_RED_MIN_AREA,
    )

    red *= road_prior

    return red.astype(np.uint8)


def mask_to_color(
    mask: np.ndarray,
    color_map: Dict[
        int,
        Tuple[int, int, int],
    ],
) -> np.ndarray:
    height, width = mask.shape

    color = np.zeros(
        (height, width, 3),
        dtype=np.uint8,
    )

    for class_id, rgb in (
        color_map.items()
    ):
        color[
            mask == class_id
        ] = rgb

    return color


def safe_ratio(
    numerator: float,
    denominator: float,
) -> float:
    if denominator <= 0:
        return 0.0

    return float(
        numerator / denominator
    )


def safe_mean(
    values: Iterable[float],
) -> float:
    values = list(values)

    return (
        float(np.mean(values))
        if values
        else 0.0
    )


def safe_min(
    values: Iterable[float],
) -> float:
    values = list(values)

    return (
        float(np.min(values))
        if values
        else 0.0
    )


def safe_max(
    values: Iterable[float],
) -> float:
    values = list(values)

    return (
        float(np.max(values))
        if values
        else 0.0
    )


def confidence_level(
    confidence: float,
) -> str:
    if confidence >= 0.80:
        return "high"

    if confidence >= 0.60:
        return "medium"

    return "low"


# ============================================================
# 7. Agent1Pipeline
# ============================================================

class Agent1Pipeline:
    def __init__(
        self,
        project_root: Optional[Path] = None,
        image_size: int = IMAGE_SIZE,
        device: Optional[str] = None,
        model_paths: Optional[Dict[str, Path]] = None,
        checkpoint_dir: Optional[Path] = None,
    ):
        self.project_root = Path(project_root or AGENT_ROOT)
        self.checkpoint_dir = Path(checkpoint_dir or CHECKPOINT_DIR)
        configured_paths = {
            key: Path(value)
            for key, value in (model_paths or {}).items()
            if value is not None
        }

        def resolve_checkpoint(
            key: str,
            candidates: Iterable[str],
            include_keywords: Iterable[str],
            exclude_keywords: Iterable[str] = (),
        ) -> Path:
            explicit = configured_paths.get(key)
            if explicit is not None:
                if not explicit.is_file():
                    raise FileNotFoundError(f"模型文件不存在：{key}={explicit}")
                return explicit
            return find_checkpoint(
                candidates,
                include_keywords=include_keywords,
                exclude_keywords=exclude_keywords,
                checkpoint_dir=self.checkpoint_dir,
            )

        self.image_size = int(
            image_size
        )

        if device is None:
            device = (
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )

        self.device = torch.device(
            device
        )

        print("=" * 100)
        print("初始化 Agent1Pipeline")
        print("=" * 100)
        print(f"device = {self.device}")
        print(
            f"image_size = "
            f"{self.image_size}"
        )

        self.building_checkpoint = (
            resolve_checkpoint(
                "building",
                BUILDING_CKPT_CANDIDATES,
                include_keywords=[
                    "building",
                    "best",
                ],
                exclude_keywords=[
                    "damage",
                    "road",
                ],
            )
        )

        self.damage_checkpoint = (
            resolve_checkpoint(
                "damage",
                DAMAGE_CKPT_CANDIDATES,
                include_keywords=[
                    "damage",
                    "best",
                ],
                exclude_keywords=[
                    "road",
                ],
            )
        )

        self.road_binary_checkpoint = (
            resolve_checkpoint(
                "road_binary",
                ROAD_BINARY_CKPT_CANDIDATES,
                include_keywords=[
                    "road",
                    "best",
                ],
                exclude_keywords=[
                    "status",
                    "attres",
                ],
            )
        )

        self.road_status_checkpoint = (
            resolve_checkpoint(
                "road_status",
                ROAD_STATUS_CKPT_CANDIDATES,
                include_keywords=[
                    "road",
                    "status",
                    "best",
                ],
            )
        )

        print(
            "building checkpoint = "
            f"{self.building_checkpoint}"
        )

        print(
            "damage checkpoint = "
            f"{self.damage_checkpoint}"
        )

        print(
            "road checkpoint = "
            f"{self.road_binary_checkpoint}"
        )

        print(
            "road status checkpoint = "
            f"{self.road_status_checkpoint}"
        )

        (
            self.building_model,
            self.building_checkpoint_data,
        ) = load_segmentation_model(
            checkpoint_path=(
                self.building_checkpoint
            ),
            model_class=BuildingUNet,
            in_channels=3,
            out_channels=1,
            device=self.device,
        )

        (
            self.damage_model,
            self.damage_checkpoint_data,
        ) = load_segmentation_model(
            checkpoint_path=(
                self.damage_checkpoint
            ),
            model_class=DamageUNet,
            in_channels=7,
            out_channels=5,
            device=self.device,
        )

        (
            self.road_model,
            self.road_checkpoint_data,
        ) = load_segmentation_model(
            checkpoint_path=(
                self.road_binary_checkpoint
            ),
            model_class=RoadUNet,
            in_channels=3,
            out_channels=1,
            device=self.device,
        )

        (
            self.road_status_model,
            self.road_status_checkpoint_data,
        ) = load_road_status_model(
            checkpoint_path=(
                self.road_status_checkpoint
            ),
            device=self.device,
        )

        print("四个模型加载完成。")
        print("=" * 100)

    # --------------------------------------------------------
    # 模型推理
    # --------------------------------------------------------

    def predict_building(
        self,
        pre_rgb: np.ndarray,
    ):
        tensor = image_to_tensor_01(
            pre_rgb
        ).unsqueeze(0).to(
            self.device
        )

        with torch.inference_mode():
            logits = self.building_model(
                tensor
            )

            probability = torch.sigmoid(
                logits
            )[0, 0].cpu().numpy()

        raw_mask = (
            probability
            >= BUILDING_THRESHOLD
        ).astype(np.uint8)

        clean_mask = clean_binary_mask(
            raw_mask,
            min_area=BUILDING_MIN_AREA,
            close_kernel=(
                BUILDING_CLOSE_KERNEL
            ),
        )

        return (
            raw_mask,
            clean_mask,
            probability.astype(np.float32),
        )

    def predict_damage(
        self,
        pre_rgb: np.ndarray,
        post_rgb: np.ndarray,
        building_mask: np.ndarray,
    ):
        pre_tensor = image_to_tensor_01(
            pre_rgb
        )

        post_tensor = image_to_tensor_01(
            post_rgb
        )

        prior_tensor = torch.from_numpy(
            building_mask.astype(
                np.float32
            )[None, :, :]
        )

        tensor = torch.cat(
            [
                pre_tensor,
                post_tensor,
                prior_tensor,
            ],
            dim=0,
        ).unsqueeze(0).to(
            self.device
        )

        with torch.inference_mode():
            logits = self.damage_model(
                tensor
            )

            if (
                logits.ndim != 4
                or logits.shape[1] != 5
            ):
                raise RuntimeError(
                    "建筑损伤模型输出形状异常："
                    f"{logits.shape}"
                )

            probabilities = F.softmax(
                logits,
                dim=1,
            )[0].cpu().numpy()

            pixel_mask = np.argmax(
                probabilities,
                axis=0,
            ).astype(np.uint8)

        pixel_mask[
            building_mask == 0
        ] = 0

        return (
            pixel_mask,
            probabilities.astype(np.float32),
        )

    def predict_road(
        self,
        pre_rgb: np.ndarray,
    ):
        tensor = image_to_tensor_01(
            pre_rgb
        ).unsqueeze(0).to(
            self.device
        )

        with torch.inference_mode():
            logits = self.road_model(
                tensor
            )

            probability = torch.sigmoid(
                logits
            )[0, 0].cpu().numpy()

        raw_mask = (
            probability
            >= ROAD_THRESHOLD
        ).astype(np.uint8)

        clean_mask = clean_binary_mask(
            raw_mask,
            min_area=ROAD_MIN_AREA,
            close_kernel=ROAD_CLOSE_KERNEL,
        )

        return (
            raw_mask,
            clean_mask,
            probability.astype(np.float32),
        )

    def predict_road_status(
        self,
        pre_rgb: np.ndarray,
        post_rgb: np.ndarray,
        road_prior: np.ndarray,
    ):
        pre_tensor = (
            image_to_tensor_minus1_1(
                pre_rgb
            )
        )

        post_tensor = (
            image_to_tensor_minus1_1(
                post_rgb
            )
        )

        prior_tensor = torch.from_numpy(
            road_prior.astype(
                np.float32
            )[None, :, :]
        )

        tensor = torch.cat(
            [
                pre_tensor,
                post_tensor,
                prior_tensor,
            ],
            dim=0,
        ).unsqueeze(0).to(
            self.device
        )

        with torch.inference_mode():
            logits = (
                self.road_status_model(
                    tensor
                )
            )

            probabilities = F.softmax(
                logits,
                dim=1,
            )[0].cpu().numpy()

            predicted_class = np.argmax(
                probabilities,
                axis=0,
            ).astype(np.uint8)

        affected_probability = (
            probabilities[2]
            .astype(np.float32)
        )

        # 保守规则：
        # 既要模型类别为2，又要概率达到阈值
        raw_red = np.logical_and(
            predicted_class == 2,
            affected_probability
            >= ROAD_AFFECTED_PROB_THRESHOLD,
        ).astype(np.uint8)

        raw_red *= (
            road_prior > 0
        ).astype(np.uint8)

        post_red = (
            postprocess_road_red(
                raw_red,
                road_prior,
            )
        )

        raw_status = np.zeros_like(
            road_prior,
            dtype=np.uint8,
        )

        raw_status[
            road_prior > 0
        ] = 1

        raw_status[
            raw_red > 0
        ] = 2

        post_status = np.zeros_like(
            road_prior,
            dtype=np.uint8,
        )

        post_status[
            road_prior > 0
        ] = 1

        post_status[
            post_red > 0
        ] = 2

        return (
            raw_status,
            post_status,
            probabilities.astype(
                np.float32
            ),
        )

    # --------------------------------------------------------
    # 建筑实例化与实例证据
    # --------------------------------------------------------

    @staticmethod
    def decide_instance_damage(
        class_counts: Dict[int, int],
        total_pixels: int,
    ) -> int:
        if total_pixels <= 0:
            return 1

        minor_ratio = (
            class_counts.get(2, 0)
            / total_pixels
        )

        major_ratio = (
            class_counts.get(3, 0)
            / total_pixels
        )

        destroyed_ratio = (
            class_counts.get(4, 0)
            / total_pixels
        )

        if (
            destroyed_ratio
            >= DESTROYED_RATIO_THRESHOLD
        ):
            return 4

        if (
            major_ratio
            > MAJOR_RATIO_THRESHOLD
        ):
            return 3

        if (
            minor_ratio
            > MINOR_RATIO_THRESHOLD
        ):
            return 2

        return 1

    def build_instances(
        self,
        building_mask: np.ndarray,
        pixel_damage_mask: np.ndarray,
        damage_probabilities: np.ndarray,
    ):
        (
            number_of_labels,
            labels,
            statistics,
            _,
        ) = cv2.connectedComponentsWithStats(
            (
                building_mask > 0
            ).astype(np.uint8),
            connectivity=8,
        )

        instance_mask = labels.astype(
            np.uint16
        )

        instance_damage_mask = np.zeros_like(
            building_mask,
            dtype=np.uint8,
        )

        core_instances = []
        uncertain_building_ids = []

        presence_confidences = []
        level_confidences = []

        distribution = {
            "no_damage": 0,
            "minor_damage": 0,
            "major_damage": 0,
            "destroyed": 0,
        }

        damaged_count = 0

        for instance_id in range(
            1,
            number_of_labels,
        ):
            area_pixels = int(
                statistics[
                    instance_id,
                    cv2.CC_STAT_AREA,
                ]
            )

            if (
                area_pixels
                < BUILDING_MIN_AREA
            ):
                instance_mask[
                    instance_mask
                    == instance_id
                ] = 0

                continue

            region = (
                instance_mask
                == instance_id
            )

            raw_values = (
                pixel_damage_mask[
                    region
                ]
            )

            counts = {
                class_id: int(
                    np.sum(
                        raw_values
                        == class_id
                    )
                )
                for class_id
                in [1, 2, 3, 4]
            }

            damage_level = (
                self.decide_instance_damage(
                    class_counts=counts,
                    total_pixels=area_pixels,
                )
            )

            instance_damage_mask[
                region
            ] = damage_level

            is_damaged = (
                damage_level
                in [2, 3, 4]
            )

            if is_damaged:
                damaged_count += 1

            level_name = (
                BUILDING_LEVEL_NAMES[
                    damage_level
                ]
            )

            distribution[
                level_name
            ] += 1

            region_probabilities = (
                damage_probabilities[
                    :,
                    region,
                ]
            )

            damage_presence_confidence = (
                float(
                    np.mean(
                        np.sum(
                            region_probabilities[
                                2:5
                            ],
                            axis=0,
                        )
                    )
                )
            )

            damage_level_confidence = (
                float(
                    np.mean(
                        region_probabilities[
                            damage_level
                        ]
                    )
                )
            )

            presence_confidences.append(
                damage_presence_confidence
            )

            level_confidences.append(
                damage_level_confidence
            )

            if (
                BUILDING_UNCERTAIN_LOW
                <= damage_presence_confidence
                <= BUILDING_UNCERTAIN_HIGH
            ):
                uncertain_building_ids.append(
                    int(instance_id)
                )

            (
                y_coordinates,
                x_coordinates,
            ) = np.where(region)

            bbox = {
                "x_min": int(
                    x_coordinates.min()
                ),
                "y_min": int(
                    y_coordinates.min()
                ),
                "x_max": int(
                    x_coordinates.max()
                ),
                "y_max": int(
                    y_coordinates.max()
                ),
            }

            core_instances.append({
                "evidence_id":
                    f"B{instance_id:04d}",

                "building_id":
                    int(instance_id),

                "area_pixels":
                    area_pixels,

                "bbox":
                    bbox,

                "is_damaged":
                    bool(is_damaged),

                "damage_presence_confidence":
                    round(
                        damage_presence_confidence,
                        6,
                    ),

                "damage_presence_confidence_level":
                    confidence_level(
                        damage_presence_confidence
                    ),

                "damage_level_id":
                    int(damage_level),

                "damage_level":
                    level_name,

                "damage_level_zh":
                    BUILDING_LEVEL_NAMES_ZH[
                        damage_level
                    ],

                "damage_level_confidence":
                    round(
                        damage_level_confidence,
                        6,
                    ),

                "damage_level_confidence_level":
                    confidence_level(
                        damage_level_confidence
                    ),

                "confidence_source":
                    "damage_softmax_probability",

                "confidence_is_calibrated":
                    False,
            })

        total_buildings = len(
            core_instances
        )

        core_summary = {
            "total_buildings":
                total_buildings,

            "damaged_buildings":
                damaged_count,

            "damage_ratio":
                safe_ratio(
                    damaged_count,
                    total_buildings,
                ),

            "damage_distribution":
                distribution,

            "damage_distribution_ratio": {
                key: safe_ratio(
                    value,
                    total_buildings,
                )
                for key, value
                in distribution.items()
            },

            "damage_presence_confidence_summary": {
                "mean_confidence":
                    safe_mean(
                        presence_confidences
                    ),

                "min_confidence":
                    safe_min(
                        presence_confidences
                    ),

                "max_confidence":
                    safe_max(
                        presence_confidences
                    ),
            },

            "damage_level_confidence_summary": {
                "mean_confidence":
                    safe_mean(
                        level_confidences
                    ),

                "min_confidence":
                    safe_min(
                        level_confidences
                    ),

                "max_confidence":
                    safe_max(
                        level_confidences
                    ),
            },

            "building_instances":
                core_instances,
        }

        review_info = {
            "uncertain_building_count":
                len(
                    uncertain_building_ids
                ),

            "uncertain_building_ratio":
                safe_ratio(
                    len(
                        uncertain_building_ids
                    ),
                    total_buildings,
                ),

            "uncertain_building_ids":
                uncertain_building_ids,

            "uncertain_interval": {
                "low":
                    BUILDING_UNCERTAIN_LOW,

                "high":
                    BUILDING_UNCERTAIN_HIGH,
            },
        }

        return (
            instance_mask,
            instance_damage_mask,
            core_summary,
            review_info,
        )

    # --------------------------------------------------------
    # 道路证据统计
    # --------------------------------------------------------

    @staticmethod
    def analyze_roads(
        road_status_mask: np.ndarray,
        affected_probability: np.ndarray,
    ):
        road_region = (
            road_status_mask > 0
        )

        intact_region = (
            road_status_mask == 1
        )

        affected_region = (
            road_status_mask == 2
        )

        total_road_pixels = int(
            np.sum(
                road_region
            )
        )

        intact_road_pixels = int(
            np.sum(
                intact_region
            )
        )

        affected_road_pixels = int(
            np.sum(
                affected_region
            )
        )

        affected_ratio = safe_ratio(
            affected_road_pixels,
            total_road_pixels,
        )

        if affected_road_pixels > 0:
            affected_confidence = float(
                np.mean(
                    affected_probability[
                        affected_region
                    ]
                )
            )

        elif total_road_pixels > 0:
            affected_confidence = float(
                np.mean(
                    1.0
                    - affected_probability[
                        road_region
                    ]
                )
            )

        else:
            affected_confidence = 0.0

        if total_road_pixels > 0:
            mean_probability_all_roads = (
                float(
                    np.mean(
                        affected_probability[
                            road_region
                        ]
                    )
                )
            )

        else:
            mean_probability_all_roads = 0.0

        is_affected = (
            affected_ratio
            >= ROAD_AFFECTED_EXIST_RATIO
        )

        if affected_ratio >= 0.70:
            impact_level = "high"

        elif affected_ratio >= 0.30:
            impact_level = "medium"

        elif (
            affected_ratio
            >= ROAD_AFFECTED_EXIST_RATIO
        ):
            impact_level = "low"

        else:
            impact_level = "none"

        core_summary = {
            "evidence_id":
                "R0001",

            "total_road_pixels":
                total_road_pixels,

            "intact_road_pixels":
                intact_road_pixels,

            "affected_road_pixels":
                affected_road_pixels,

            "affected_road_ratio":
                affected_ratio,

            "is_affected":
                bool(is_affected),

            "affected_presence_confidence":
                affected_confidence,

            "affected_presence_confidence_level":
                confidence_level(
                    affected_confidence
                ),

            "mean_affected_probability_on_all_roads":
                mean_probability_all_roads,

            "road_impact_level":
                impact_level,

            "confidence_source":
                "road_status_softmax_probability",

            "confidence_is_calibrated":
                False,

            "interpretation_note": (
                "红色道路表示疑似受灾影响或"
                "存在通行受阻风险，不等同于"
                "已经确认的结构性道路损毁。"
            ),
        }

        uncertain_region = (
            road_region
            & (
                affected_probability
                >= ROAD_UNCERTAIN_LOW
            )
            & (
                affected_probability
                <= ROAD_UNCERTAIN_HIGH
            )
        )

        uncertain_pixels = int(
            np.sum(
                uncertain_region
            )
        )

        uncertain_ratio = safe_ratio(
            uncertain_pixels,
            total_road_pixels,
        )

        review_info = {
            "uncertain_road_pixels":
                uncertain_pixels,

            "uncertain_road_ratio":
                uncertain_ratio,

            "affected_presence_uncertain":
                bool(
                    ROAD_UNCERTAIN_LOW
                    <= affected_confidence
                    <= ROAD_UNCERTAIN_HIGH
                ),

            "uncertain_probability_interval": {
                "low":
                    ROAD_UNCERTAIN_LOW,

                "high":
                    ROAD_UNCERTAIN_HIGH,
            },

            "high_affected_ratio_flag":
                bool(
                    affected_ratio
                    >= ROAD_HIGH_RATIO_REVIEW
                ),
        }

        return (
            core_summary,
            review_info,
        )

    # --------------------------------------------------------
    # 风险与融合
    # --------------------------------------------------------

    @staticmethod
    def calculate_building_risk(
        building_summary: Dict[
            str,
            Any,
        ],
    ) -> str:
        total_buildings = (
            building_summary[
                "total_buildings"
            ]
        )

        distribution = (
            building_summary[
                "damage_distribution"
            ]
        )

        major = distribution[
            "major_damage"
        ]

        destroyed = distribution[
            "destroyed"
        ]

        severe_ratio = safe_ratio(
            major + destroyed,
            total_buildings,
        )

        damaged_ratio = (
            building_summary[
                "damage_ratio"
            ]
        )

        if (
            destroyed > 0
            or severe_ratio >= 0.30
        ):
            return "high"

        if (
            severe_ratio >= 0.10
            or damaged_ratio >= 0.30
        ):
            return "medium"

        if damaged_ratio > 0:
            return "low"

        return "none"

    @staticmethod
    def calculate_scene_risk(
        building_risk: str,
        road_risk: str,
    ) -> str:
        score_map = {
            "none": 0,
            "low": 1,
            "medium": 2,
            "high": 3,
        }

        reverse_map = {
            0: "none",
            1: "low",
            2: "medium",
            3: "high",
        }

        score = max(
            score_map[
                building_risk
            ],
            score_map[
                road_risk
            ],
        )

        return reverse_map[
            score
        ]

    @staticmethod
    def create_fused_mask(
        building_damage_mask: np.ndarray,
        road_status_mask: np.ndarray,
    ) -> np.ndarray:
        fused_mask = np.zeros_like(
            building_damage_mask,
            dtype=np.uint8,
        )

        # 道路先画
        fused_mask[
            road_status_mask == 1
        ] = 1

        fused_mask[
            road_status_mask == 2
        ] = 2

        # 建筑后画，覆盖道路
        fused_mask[
            building_damage_mask == 1
        ] = 10

        fused_mask[
            building_damage_mask == 2
        ] = 11

        fused_mask[
            building_damage_mask == 3
        ] = 12

        fused_mask[
            building_damage_mask == 4
        ] = 13

        return fused_mask

    @staticmethod
    def create_darkened_overlay(
        post_rgb: np.ndarray,
        building_damage_mask: np.ndarray,
        road_status_mask: np.ndarray,
    ) -> np.ndarray:
        overlay = (
            post_rgb.astype(
                np.float32
            )
            * BACKGROUND_DARKEN_FACTOR
        )

        road_colors = {
            1: np.array(
                [255, 255, 255],
                dtype=np.float32,
            ),
            2: np.array(
                [255, 0, 0],
                dtype=np.float32,
            ),
        }

        for class_id, color in (
            road_colors.items()
        ):
            region = (
                road_status_mask
                == class_id
            )

            overlay[
                region
            ] = (
                overlay[region]
                * (
                    1.0
                    - ROAD_OVERLAY_ALPHA
                )
                + color
                * ROAD_OVERLAY_ALPHA
            )

        building_colors = {
            class_id: np.array(
                rgb,
                dtype=np.float32,
            )
            for class_id, rgb
            in BUILDING_COLORS.items()
            if class_id != 0
        }

        for class_id, color in (
            building_colors.items()
        ):
            region = (
                building_damage_mask
                == class_id
            )

            overlay[
                region
            ] = (
                overlay[region]
                * (
                    1.0
                    - BUILDING_OVERLAY_ALPHA
                )
                + color
                * BUILDING_OVERLAY_ALPHA
            )

        return np.clip(
            overlay,
            0,
            255,
        ).astype(np.uint8)

    # --------------------------------------------------------
    # JSON 输出
    # --------------------------------------------------------

    @staticmethod
    def create_core_ledger(
        sample_id: str,
        pre_path: Path,
        post_path: Path,
        building_summary: Dict[
            str,
            Any,
        ],
        road_summary: Dict[
            str,
            Any,
        ],
        building_risk: str,
        road_risk: str,
        scene_risk: str,
        output_paths: Dict[
            str,
            str,
        ],
        model_metadata: Dict[
            str,
            str,
        ],
    ) -> Dict[str, Any]:
        """
        给 Agent3。
        不包含不确定性、人工复核结论。
        """
        return {
            "schema_version":
                "2.1",

            "agent": {
                "agent_id":
                    "agent1",

                "agent_name":
                    "时空视觉证据感知与证据账本生成智能体",
            },

            "sample_id":
                sample_id,

            "input_images": {
                "pre_image":
                    str(pre_path),

                "post_image":
                    str(post_path),
            },

            "building_evidence":
                building_summary,

            "road_evidence":
                road_summary,

            "derived_assessment": {
                "building_risk_level":
                    building_risk,

                "road_impact_level":
                    road_risk,

                "scene_risk_level":
                    scene_risk,
            },

            "evidence_images": {
                "fused_color":
                    output_paths[
                        "fused_color"
                    ],

                "fused_overlay":
                    output_paths[
                        "fused_overlay"
                    ],
            },

            "output_files":
                output_paths,

            "model_metadata":
                model_metadata,

            "confidence_metadata": {
                "building_confidence_policy": (
                    "建筑是否受损和具体损伤等级"
                    "均输出模型置信度；具体损伤"
                    "等级不输出不确定标签。"
                ),

                "road_confidence_policy": (
                    "道路受影响判断输出模型"
                    "softmax 置信度。"
                ),

                "calibration_warning": (
                    "模型置信度尚未经过概率校准，"
                    "不得直接解释为真实正确概率。"
                ),
            },
        }

    @staticmethod
    def create_report_summary(
        sample_id: str,
        building_summary: Dict[
            str,
            Any,
        ],
        road_summary: Dict[
            str,
            Any,
        ],
        building_risk: str,
        road_risk: str,
        scene_risk: str,
        output_paths: Dict[
            str,
            str,
        ],
    ) -> Dict[str, Any]:
        """
        给 Agent4 的场景级统计。
        """
        distribution = (
            building_summary[
                "damage_distribution"
            ]
        )

        return {
            "schema_version":
                "1.1",

            "sample_id":
                sample_id,

            "building_summary": {
                "total_buildings":
                    building_summary[
                        "total_buildings"
                    ],

                "damaged_buildings":
                    building_summary[
                        "damaged_buildings"
                    ],

                "damage_ratio":
                    building_summary[
                        "damage_ratio"
                    ],

                "no_damage_buildings":
                    distribution[
                        "no_damage"
                    ],

                "minor_damage_buildings":
                    distribution[
                        "minor_damage"
                    ],

                "major_damage_buildings":
                    distribution[
                        "major_damage"
                    ],

                "destroyed_buildings":
                    distribution[
                        "destroyed"
                    ],

                "mean_damage_presence_confidence":
                    building_summary[
                        "damage_presence_confidence_summary"
                    ]["mean_confidence"],

                "mean_damage_level_confidence":
                    building_summary[
                        "damage_level_confidence_summary"
                    ]["mean_confidence"],
            },

            "road_summary": {
                "is_affected":
                    road_summary[
                        "is_affected"
                    ],

                "total_road_pixels":
                    road_summary[
                        "total_road_pixels"
                    ],

                "affected_road_pixels":
                    road_summary[
                        "affected_road_pixels"
                    ],

                "affected_road_ratio":
                    road_summary[
                        "affected_road_ratio"
                    ],

                "affected_presence_confidence":
                    road_summary[
                        "affected_presence_confidence"
                    ],

                "interpretation_note":
                    road_summary[
                        "interpretation_note"
                    ],
            },

            "overall_assessment": {
                "building_risk_level":
                    building_risk,

                "road_impact_level":
                    road_risk,

                "scene_risk_level":
                    scene_risk,
            },

            "evidence_images": {
                "fused_color":
                    output_paths[
                        "fused_color"
                    ],

                "fused_overlay":
                    output_paths[
                        "fused_overlay"
                    ],
            },
        }

    @staticmethod
    def create_review_flags(
        sample_id: str,
        building_review: Dict[
            str,
            Any,
        ],
        road_review: Dict[
            str,
            Any,
        ],
    ) -> Dict[str, Any]:
        """
        只给 Agent4。
        """
        review_reasons = []

        if (
            building_review[
                "uncertain_building_count"
            ] > 0
        ):
            review_reasons.append({
                "type":
                    "building_damage_presence_uncertainty",

                "message": (
                    f"共有 "
                    f"{building_review['uncertain_building_count']} "
                    f"栋建筑的是否受损判断"
                    f"处于临界置信度区间。"
                ),

                "affected_building_ids":
                    building_review[
                        "uncertain_building_ids"
                    ],
            })

        if (
            road_review[
                "uncertain_road_ratio"
            ]
            >= ROAD_UNCERTAIN_REVIEW_RATIO
        ):
            review_reasons.append({
                "type":
                    "road_status_uncertainty",

                "message": (
                    "道路状态模型存在较多临界"
                    "概率像素，建议人工核查"
                    "局部道路区域。"
                ),

                "uncertain_road_ratio":
                    road_review[
                        "uncertain_road_ratio"
                    ],
            })

        if road_review[
            "affected_presence_uncertain"
        ]:
            review_reasons.append({
                "type":
                    "road_affected_presence_uncertainty",

                "message": (
                    "道路是否受影响的场景级判断"
                    "处于临界置信度范围。"
                ),
            })

        if road_review[
            "high_affected_ratio_flag"
        ]:
            review_reasons.append({
                "type":
                    "possible_cross_domain_overprediction",

                "message": (
                    "道路受影响比例极高，建议"
                    "排查跨数据集迁移造成的"
                    "过预测。"
                ),
            })

        review_required = (
            len(review_reasons) > 0
        )

        return {
            "schema_version":
                "1.1",

            "sample_id":
                sample_id,

            "review_required":
                review_required,

            "uncertainty_summary": {
                "uncertain_building_count":
                    building_review[
                        "uncertain_building_count"
                    ],

                "uncertain_building_ratio":
                    building_review[
                        "uncertain_building_ratio"
                    ],

                "uncertain_building_ids":
                    building_review[
                        "uncertain_building_ids"
                    ],

                "uncertain_road_pixels":
                    road_review[
                        "uncertain_road_pixels"
                    ],

                "uncertain_road_ratio":
                    road_review[
                        "uncertain_road_ratio"
                    ],
            },

            "review_reasons":
                review_reasons,

            "report_instruction": {
                "must_include_manual_review_note":
                    review_required,

                "recommended_wording": (
                    "该区域部分自动识别结果存在"
                    "不确定性，建议结合人工判读"
                    "及其他数据源进行进一步复核。"
                    if review_required
                    else ""
                ),
            },

            "routing": {
                "intended_recipient":
                    "agent4_report_generation",

                "do_not_send_to": [
                    "agent2_description_generation",
                    "agent3_evidence_verification",
                ],
            },
        }

    # --------------------------------------------------------
    # 可视化
    # --------------------------------------------------------

    @staticmethod
    def create_compare_image(
        pre_rgb: np.ndarray,
        post_rgb: np.ndarray,
        building_damage_mask: np.ndarray,
        road_status_mask: np.ndarray,
        fused_color: np.ndarray,
        fused_overlay: np.ndarray,
        sample_id: str,
        save_path: Path,
    ):
        height, width = (
            building_damage_mask.shape
        )

        building_color = (
            mask_to_color(
                building_damage_mask,
                BUILDING_COLORS,
            )
        )

        road_color = (
            mask_to_color(
                road_status_mask,
                ROAD_STATUS_COLORS,
            )
        )

        canvas = Image.new(
            "RGB",
            (
                width * 3,
                height * 2,
            ),
            (0, 0, 0),
        )

        draw = ImageDraw.Draw(
            canvas
        )

        items = [
            (pre_rgb, "Pre image"),
            (post_rgb, "Post image"),
            (
                building_color,
                "Building damage",
            ),
            (
                road_color,
                "Road status",
            ),
            (
                fused_color,
                "Fused evidence",
            ),
            (
                fused_overlay,
                "Darkened fused overlay",
            ),
        ]

        for index, (
            image,
            title,
        ) in enumerate(items):
            row = index // 3
            column = index % 3

            x0 = column * width
            y0 = row * height

            canvas.paste(
                Image.fromarray(
                    image.astype(
                        np.uint8
                    )
                ),
                (x0, y0),
            )

            draw.text(
                (
                    x0 + 10,
                    y0 + 10,
                ),
                title,
                fill=(
                    255,
                    255,
                    255,
                ),
            )

        draw.text(
            (
                10,
                height * 2 - 28,
            ),
            sample_id,
            fill=(
                255,
                255,
                255,
            ),
        )

        canvas.save(
            save_path
        )

    # --------------------------------------------------------
    # 单样本完整运行
    # --------------------------------------------------------

    def run_one(
        self,
        pre_image_path: Path,
        post_image_path: Path,
        sample_id: str,
        output_root: Path = (
            DEFAULT_OUTPUT_ROOT
        ),
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        pre_image_path = Path(
            pre_image_path
        )

        post_image_path = Path(
            post_image_path
        )

        output_root = Path(
            output_root
        )

        if not pre_image_path.exists():
            raise FileNotFoundError(
                "找不到灾前图像："
                f"{pre_image_path}"
            )

        if not post_image_path.exists():
            raise FileNotFoundError(
                "找不到灾后图像："
                f"{post_image_path}"
            )

        sample_root = (
            output_root
            / sample_id
        )

        if (
            sample_root.exists()
            and overwrite
        ):
            shutil.rmtree(
                sample_root
            )

        input_dir = (
            sample_root
            / "input"
        )

        building_dir = (
            sample_root
            / "building"
        )

        road_dir = (
            sample_root
            / "road"
        )

        fusion_dir = (
            sample_root
            / "fusion"
        )

        for_agent3_dir = (
            sample_root
            / "for_agent3"
        )

        for_agent4_dir = (
            sample_root
            / "for_agent4"
        )

        for folder in [
            input_dir,
            building_dir,
            road_dir,
            fusion_dir,
            for_agent3_dir,
            for_agent4_dir,
        ]:
            folder.mkdir(
                parents=True,
                exist_ok=True,
            )

        pre_rgb = load_rgb(
            pre_image_path,
            self.image_size,
        )

        post_rgb = load_rgb(
            post_image_path,
            self.image_size,
        )

        pre_input_path = (
            input_dir
            / "pre_image.png"
        )

        post_input_path = (
            input_dir
            / "post_image.png"
        )

        Image.fromarray(
            pre_rgb
        ).save(
            pre_input_path
        )

        Image.fromarray(
            post_rgb
        ).save(
            post_input_path
        )

        # 1. 建筑分割
        (
            building_raw_mask,
            building_clean_mask,
            building_probability,
        ) = self.predict_building(
            pre_rgb
        )

        # 2. 建筑损伤
        (
            damage_pixel_mask,
            damage_probabilities,
        ) = self.predict_damage(
            pre_rgb,
            post_rgb,
            building_clean_mask,
        )

        # 3. 建筑实例化
        (
            building_instance_mask,
            damage_instance_mask,
            building_core,
            building_review,
        ) = self.build_instances(
            building_mask=(
                building_clean_mask
            ),
            pixel_damage_mask=(
                damage_pixel_mask
            ),
            damage_probabilities=(
                damage_probabilities
            ),
        )

        # 4. 道路分割
        (
            road_raw_mask,
            road_clean_mask,
            road_probability,
        ) = self.predict_road(
            pre_rgb
        )

        # 5. 道路状态
        (
            road_status_raw,
            road_status_post,
            road_status_probabilities,
        ) = self.predict_road_status(
            pre_rgb=pre_rgb,
            post_rgb=post_rgb,
            road_prior=(
                road_clean_mask
            ),
        )

        (
            road_core,
            road_review,
        ) = self.analyze_roads(
            road_status_mask=(
                road_status_post
            ),
            affected_probability=(
                road_status_probabilities[
                    2
                ]
            ),
        )

        # 6. 风险和融合
        building_risk = (
            self.calculate_building_risk(
                building_core
            )
        )

        road_risk = (
            road_core[
                "road_impact_level"
            ]
        )

        scene_risk = (
            self.calculate_scene_risk(
                building_risk,
                road_risk,
            )
        )

        fused_mask = (
            self.create_fused_mask(
                building_damage_mask=(
                    damage_instance_mask
                ),
                road_status_mask=(
                    road_status_post
                ),
            )
        )

        fused_color = mask_to_color(
            fused_mask,
            FUSED_COLORS,
        )

        fused_overlay = (
            self.create_darkened_overlay(
                post_rgb=post_rgb,
                building_damage_mask=(
                    damage_instance_mask
                ),
                road_status_mask=(
                    road_status_post
                ),
            )
        )

        # ----------------------------------------------------
        # 保存建筑输出
        # ----------------------------------------------------

        building_paths = {
            "building_raw_mask":
                building_dir
                / "building_raw_mask.png",

            "building_clean_mask":
                building_dir
                / "building_clean_mask.png",

            "building_probability":
                building_dir
                / "building_probability.npy",

            "damage_pixel_mask":
                building_dir
                / "damage_pixel_mask.png",

            "damage_probabilities":
                building_dir
                / "damage_probabilities.npz",

            "building_instance_mask":
                building_dir
                / "building_instance_mask.png",

            "damage_instance_mask":
                building_dir
                / "damage_instance_mask.png",

            "damage_instance_color":
                building_dir
                / "damage_instance_color.png",
        }

        cv2.imwrite(
            str(
                building_paths[
                    "building_raw_mask"
                ]
            ),
            building_raw_mask,
        )

        cv2.imwrite(
            str(
                building_paths[
                    "building_clean_mask"
                ]
            ),
            building_clean_mask,
        )

        np.save(
            building_paths[
                "building_probability"
            ],
            building_probability,
        )

        cv2.imwrite(
            str(
                building_paths[
                    "damage_pixel_mask"
                ]
            ),
            damage_pixel_mask,
        )

        np.savez_compressed(
            building_paths[
                "damage_probabilities"
            ],
            probabilities=(
                damage_probabilities
            ),
        )

        cv2.imwrite(
            str(
                building_paths[
                    "building_instance_mask"
                ]
            ),
            building_instance_mask,
        )

        cv2.imwrite(
            str(
                building_paths[
                    "damage_instance_mask"
                ]
            ),
            damage_instance_mask,
        )

        Image.fromarray(
            mask_to_color(
                damage_instance_mask,
                BUILDING_COLORS,
            )
        ).save(
            building_paths[
                "damage_instance_color"
            ]
        )

        # ----------------------------------------------------
        # 保存道路输出
        # ----------------------------------------------------

        road_paths = {
            "road_raw_mask":
                road_dir
                / "road_raw_mask.png",

            "road_clean_mask":
                road_dir
                / "road_clean_mask.png",

            "road_probability":
                road_dir
                / "road_probability.npy",

            "road_status_raw_mask":
                road_dir
                / "road_status_raw_mask.png",

            "road_status_post_mask":
                road_dir
                / "road_status_post_mask.png",

            "road_status_color":
                road_dir
                / "road_status_color.png",

            "road_status_probabilities":
                road_dir
                / "road_status_probabilities.npz",

            "road_affected_probability":
                road_dir
                / "road_affected_probability.png",
        }

        cv2.imwrite(
            str(
                road_paths[
                    "road_raw_mask"
                ]
            ),
            road_raw_mask,
        )

        cv2.imwrite(
            str(
                road_paths[
                    "road_clean_mask"
                ]
            ),
            road_clean_mask,
        )

        np.save(
            road_paths[
                "road_probability"
            ],
            road_probability,
        )

        cv2.imwrite(
            str(
                road_paths[
                    "road_status_raw_mask"
                ]
            ),
            road_status_raw,
        )

        cv2.imwrite(
            str(
                road_paths[
                    "road_status_post_mask"
                ]
            ),
            road_status_post,
        )

        Image.fromarray(
            mask_to_color(
                road_status_post,
                ROAD_STATUS_COLORS,
            )
        ).save(
            road_paths[
                "road_status_color"
            ]
        )

        np.savez_compressed(
            road_paths[
                "road_status_probabilities"
            ],
            probabilities=(
                road_status_probabilities
            ),
        )

        affected_probability_uint8 = (
            np.clip(
                road_status_probabilities[
                    2
                ] * 255.0,
                0,
                255,
            )
            .astype(np.uint8)
        )

        cv2.imwrite(
            str(
                road_paths[
                    "road_affected_probability"
                ]
            ),
            affected_probability_uint8,
        )

        # ----------------------------------------------------
        # 保存融合输出
        # ----------------------------------------------------

        fusion_paths = {
            "fused_mask":
                fusion_dir
                / "fused_mask.png",

            "fused_color":
                fusion_dir
                / "fused_color.png",

            "fused_overlay":
                fusion_dir
                / "fused_overlay.png",

            "visual_compare":
                fusion_dir
                / "visual_compare.png",
        }

        cv2.imwrite(
            str(
                fusion_paths[
                    "fused_mask"
                ]
            ),
            fused_mask,
        )

        Image.fromarray(
            fused_color
        ).save(
            fusion_paths[
                "fused_color"
            ]
        )

        Image.fromarray(
            fused_overlay
        ).save(
            fusion_paths[
                "fused_overlay"
            ]
        )

        self.create_compare_image(
            pre_rgb=pre_rgb,
            post_rgb=post_rgb,
            building_damage_mask=(
                damage_instance_mask
            ),
            road_status_mask=(
                road_status_post
            ),
            fused_color=fused_color,
            fused_overlay=(
                fused_overlay
            ),
            sample_id=sample_id,
            save_path=(
                fusion_paths[
                    "visual_compare"
                ]
            ),
        )

        # ----------------------------------------------------
        # 给后续智能体的输出
        # ----------------------------------------------------

        output_paths = {
            "building_instance_mask":
                str(
                    building_paths[
                        "building_instance_mask"
                    ]
                ),

            "damage_instance_mask":
                str(
                    building_paths[
                        "damage_instance_mask"
                    ]
                ),

            "damage_instance_color":
                str(
                    building_paths[
                        "damage_instance_color"
                    ]
                ),

            "road_status_post_mask":
                str(
                    road_paths[
                        "road_status_post_mask"
                    ]
                ),

            "road_status_color":
                str(
                    road_paths[
                        "road_status_color"
                    ]
                ),

            "fused_mask":
                str(
                    fusion_paths[
                        "fused_mask"
                    ]
                ),

            "fused_color":
                str(
                    fusion_paths[
                        "fused_color"
                    ]
                ),

            "fused_overlay":
                str(
                    fusion_paths[
                        "fused_overlay"
                    ]
                ),

            "visual_compare":
                str(
                    fusion_paths[
                        "visual_compare"
                    ]
                ),
        }

        model_metadata = {
            "building_checkpoint":
                str(
                    self.building_checkpoint
                ),

            "damage_checkpoint":
                str(
                    self.damage_checkpoint
                ),

            "road_checkpoint":
                str(
                    self.road_binary_checkpoint
                ),

            "road_status_checkpoint":
                str(
                    self.road_status_checkpoint
                ),
        }

        core_ledger = (
            self.create_core_ledger(
                sample_id=sample_id,
                pre_path=pre_input_path,
                post_path=post_input_path,
                building_summary=(
                    building_core
                ),
                road_summary=road_core,
                building_risk=(
                    building_risk
                ),
                road_risk=road_risk,
                scene_risk=scene_risk,
                output_paths=(
                    output_paths
                ),
                model_metadata=(
                    model_metadata
                ),
            )
        )

        report_summary = (
            self.create_report_summary(
                sample_id=sample_id,
                building_summary=(
                    building_core
                ),
                road_summary=road_core,
                building_risk=(
                    building_risk
                ),
                road_risk=road_risk,
                scene_risk=scene_risk,
                output_paths=(
                    output_paths
                ),
            )
        )

        review_flags = (
            self.create_review_flags(
                sample_id=sample_id,
                building_review=(
                    building_review
                ),
                road_review=(
                    road_review
                ),
            )
        )

        core_ledger_path = (
            for_agent3_dir
            / "evidence_ledger_core.json"
        )

        agent3_manifest_path = (
            for_agent3_dir
            / "agent3_input_manifest.json"
        )

        report_summary_path = (
            for_agent4_dir
            / "agent1_report_summary.json"
        )

        review_flags_path = (
            for_agent4_dir
            / "review_flags.json"
        )

        with open(
            core_ledger_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                core_ledger,
                file,
                ensure_ascii=False,
                indent=2,
            )

        agent3_manifest = {
            "sample_id":
                sample_id,

            "required_inputs_from_agent1": {
                "evidence_ledger_core":
                    str(
                        core_ledger_path
                    ),

                "fused_color":
                    str(
                        fusion_paths[
                            "fused_color"
                        ]
                    ),

                "fused_overlay":
                    str(
                        fusion_paths[
                            "fused_overlay"
                        ]
                    ),
            },

            "additional_input_from_agent2": {
                "description_and_claims":
                    None,
            },
        }

        with open(
            agent3_manifest_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                agent3_manifest,
                file,
                ensure_ascii=False,
                indent=2,
            )

        with open(
            report_summary_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report_summary,
                file,
                ensure_ascii=False,
                indent=2,
            )

        with open(
            review_flags_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                review_flags,
                file,
                ensure_ascii=False,
                indent=2,
            )

        run_manifest = {
            "schema_version":
                "1.0",

            "sample_id":
                sample_id,

            "status":
                "success",

            "input": {
                "pre_image_source":
                    str(
                        pre_image_path
                    ),

                "post_image_source":
                    str(
                        post_image_path
                    ),

                "pre_image_copy":
                    str(
                        pre_input_path
                    ),

                "post_image_copy":
                    str(
                        post_input_path
                    ),
            },

            "agent_routing": {
                "agent2": {
                    "inputs": [
                        str(
                            pre_input_path
                        ),
                        str(
                            post_input_path
                        ),
                    ],

                    "note": (
                        "Agent2 不读取 Agent1 "
                        "的融合图或 JSON。"
                    ),
                },

                "agent3": {
                    "inputs": [
                        str(
                            core_ledger_path
                        ),
                        str(
                            fusion_paths[
                                "fused_color"
                            ]
                        ),
                        str(
                            fusion_paths[
                                "fused_overlay"
                            ]
                        ),
                    ],

                    "plus": (
                        "Agent2 输出的 "
                        "description 与 claims"
                    ),
                },

                "agent4": {
                    "inputs": [
                        str(
                            report_summary_path
                        ),
                        str(
                            review_flags_path
                        ),
                    ],

                    "plus": (
                        "Agent3 校验结果与"
                        "修正描述"
                    ),
                },
            },

            "outputs": {
                "building": {
                    key: str(value)
                    for key, value
                    in building_paths.items()
                },

                "road": {
                    key: str(value)
                    for key, value
                    in road_paths.items()
                },

                "fusion": {
                    key: str(value)
                    for key, value
                    in fusion_paths.items()
                },

                "for_agent3": {
                    "evidence_ledger_core":
                        str(
                            core_ledger_path
                        ),

                    "agent3_input_manifest":
                        str(
                            agent3_manifest_path
                        ),
                },

                "for_agent4": {
                    "agent1_report_summary":
                        str(
                            report_summary_path
                        ),

                    "review_flags":
                        str(
                            review_flags_path
                        ),
                },
            },

            "summary": {
                "total_buildings":
                    building_core[
                        "total_buildings"
                    ],

                "damaged_buildings":
                    building_core[
                        "damaged_buildings"
                    ],

                "building_damage_ratio":
                    building_core[
                        "damage_ratio"
                    ],

                "affected_road_ratio":
                    road_core[
                        "affected_road_ratio"
                    ],

                "scene_risk_level":
                    scene_risk,

                "review_required":
                    review_flags[
                        "review_required"
                    ],
            },
        }

        run_manifest_path = (
            sample_root
            / "run_manifest.json"
        )

        with open(
            run_manifest_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                run_manifest,
                file,
                ensure_ascii=False,
                indent=2,
            )

        return {
            "sample_id":
                sample_id,

            "sample_root":
                str(
                    sample_root
                ),

            "status":
                "success",

            "total_buildings":
                building_core[
                    "total_buildings"
                ],

            "damaged_buildings":
                building_core[
                    "damaged_buildings"
                ],

            "building_damage_ratio":
                building_core[
                    "damage_ratio"
                ],

            "affected_road_ratio":
                road_core[
                    "affected_road_ratio"
                ],

            "scene_risk_level":
                scene_risk,

            "review_required":
                review_flags[
                    "review_required"
                ],

            "run_manifest":
                str(
                    run_manifest_path
                ),

            "agent3_ledger":
                str(
                    core_ledger_path
                ),

            "agent4_summary":
                str(
                    report_summary_path
                ),

            "agent4_review_flags":
                str(
                    review_flags_path
                ),
        }


# ============================================================
# 8. 命令行入口
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "运行 Agent1 单样本完整推理流程。"
        )
    )

    parser.add_argument(
        "--pre_image",
        required=True,
        help="灾前图像路径。",
    )

    parser.add_argument(
        "--post_image",
        required=True,
        help="灾后图像路径。",
    )

    parser.add_argument(
        "--sample_id",
        required=True,
        help="样本编号。",
    )

    parser.add_argument(
        "--output_root",
        default=str(
            DEFAULT_OUTPUT_ROOT
        ),
        help="输出根目录。",
    )

    parser.add_argument(
        "--device",
        default=None,
        help=(
            "cuda 或 cpu，默认自动选择。"
        ),
    )

    parser.add_argument("--checkpoint_dir", default=str(CHECKPOINT_DIR))
    parser.add_argument("--building_model")
    parser.add_argument("--damage_model")
    parser.add_argument("--road_binary_model")
    parser.add_argument("--road_status_model")

    return parser.parse_args()


def main():
    args = parse_args()

    pipeline = Agent1Pipeline(
        image_size=IMAGE_SIZE,
        device=args.device,
        checkpoint_dir=Path(args.checkpoint_dir),
        model_paths={
            "building": args.building_model,
            "damage": args.damage_model,
            "road_binary": args.road_binary_model,
            "road_status": args.road_status_model,
        },
    )

    result = pipeline.run_one(
        pre_image_path=Path(
            args.pre_image
        ),
        post_image_path=Path(
            args.post_image
        ),
        sample_id=args.sample_id,
        output_root=Path(
            args.output_root
        ),
        overwrite=True,
    )

    print("=" * 100)
    print("Agent1 单样本运行完成")
    print("=" * 100)

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
