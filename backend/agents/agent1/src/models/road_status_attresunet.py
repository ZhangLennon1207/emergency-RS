"""Attention ResUNet used by the final three-class road-status checkpoint."""

from __future__ import annotations

import torch
import torch.nn.functional as functional
from torch import nn


class SEBlock(nn.Module):
    def __init__(self, channels: int, reduction: int = 16) -> None:
        super().__init__()
        hidden = max(channels // reduction, 8)
        self.fc = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, hidden, 1),
            nn.ReLU(inplace=True),
            nn.Conv2d(hidden, channels, 1),
            nn.Sigmoid(),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return inputs * self.fc(inputs)


class ResBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.se = SEBlock(out_channels)
        self.shortcut = (
            nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1, bias=False),
                nn.BatchNorm2d(out_channels),
            )
            if in_channels != out_channels
            else nn.Identity()
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        residual = self.shortcut(inputs)
        output = self.relu(self.bn1(self.conv1(inputs)))
        output = self.se(self.bn2(self.conv2(output)))
        return self.relu(output + residual)


class ASPP(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.branch1 = self._branch(in_channels, out_channels, 1, 0, 1)
        self.branch2 = self._branch(in_channels, out_channels, 3, 2, 2)
        self.branch3 = self._branch(in_channels, out_channels, 3, 4, 4)
        self.branch4 = self._branch(in_channels, out_channels, 3, 6, 6)
        self.project = self._branch(out_channels * 4, out_channels, 1, 0, 1)

    @staticmethod
    def _branch(
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        padding: int,
        dilation: int,
    ) -> nn.Sequential:
        return nn.Sequential(
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size,
                padding=padding,
                dilation=dilation,
                bias=False,
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.project(
            torch.cat(
                [
                    self.branch1(inputs),
                    self.branch2(inputs),
                    self.branch3(inputs),
                    self.branch4(inputs),
                ],
                dim=1,
            )
        )


class AttentionGate(nn.Module):
    def __init__(self, gate_channels: int, skip_channels: int, inter_channels: int) -> None:
        super().__init__()
        self.gate_conv = nn.Sequential(
            nn.Conv2d(gate_channels, inter_channels, 1, bias=False),
            nn.BatchNorm2d(inter_channels),
        )
        self.skip_conv = nn.Sequential(
            nn.Conv2d(skip_channels, inter_channels, 1, bias=False),
            nn.BatchNorm2d(inter_channels),
        )
        self.psi = nn.Sequential(nn.Conv2d(inter_channels, 1, 1), nn.Sigmoid())
        self.relu = nn.ReLU(inplace=True)

    def forward(self, gate: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        gate_value = self.gate_conv(gate)
        skip_value = self.skip_conv(skip)
        if gate_value.shape[-2:] != skip_value.shape[-2:]:
            gate_value = functional.interpolate(
                gate_value,
                size=skip_value.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
        return skip * self.psi(self.relu(gate_value + skip_value))


class UpBlock(nn.Module):
    def __init__(self, in_channels: int, skip_channels: int, out_channels: int) -> None:
        super().__init__()
        self.up = nn.ConvTranspose2d(in_channels, out_channels, 2, stride=2)
        self.att = AttentionGate(
            out_channels,
            skip_channels,
            max(out_channels // 2, 16),
        )
        self.conv = ResBlock(out_channels + skip_channels, out_channels)

    def forward(self, inputs: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        output = self.up(inputs)
        if output.shape[-2:] != skip.shape[-2:]:
            output = functional.interpolate(
                output,
                size=skip.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
        return self.conv(torch.cat([output, self.att(output, skip)], dim=1))


class AttentionResUNet7ch(nn.Module):
    def __init__(
        self,
        in_channels: int = 7,
        num_classes: int = 3,
        base_channels: int = 32,
    ) -> None:
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
        self.bottleneck = nn.Sequential(ResBlock(b * 8, b * 16), ASPP(b * 16, b * 16))
        self.dec4 = UpBlock(b * 16, b * 8, b * 8)
        self.dec3 = UpBlock(b * 8, b * 4, b * 4)
        self.dec2 = UpBlock(b * 4, b * 2, b * 2)
        self.dec1 = UpBlock(b * 2, b, b)
        self.out_conv = nn.Conv2d(b, num_classes, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        enc1 = self.enc1(inputs)
        enc2 = self.enc2(self.pool1(enc1))
        enc3 = self.enc3(self.pool2(enc2))
        enc4 = self.enc4(self.pool3(enc3))
        bottleneck = self.bottleneck(self.pool4(enc4))
        dec4 = self.dec4(bottleneck, enc4)
        dec3 = self.dec3(dec4, enc3)
        dec2 = self.dec2(dec3, enc2)
        dec1 = self.dec1(dec2, enc1)
        return self.out_conv(dec1)
