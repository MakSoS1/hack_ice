from __future__ import annotations

import torch
import torch.nn as nn


def _make_norm(norm: str, channels: int) -> nn.Module:
    if norm == "group":
        groups = min(8, channels)
        while groups > 1 and channels % groups != 0:
            groups -= 1
        return nn.GroupNorm(num_groups=max(1, groups), num_channels=channels)
    return nn.BatchNorm2d(channels)


class SEBlock(nn.Module):
    def __init__(self, channels: int, reduction: int = 8):
        super().__init__()
        hidden = max(4, channels // reduction)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Sequential(
            nn.Conv2d(channels, hidden, kernel_size=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(hidden, channels, kernel_size=1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        w = self.fc(self.pool(x))
        return x * w


class ResidualConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, *, dilation: int = 1, norm: str = "batch"):
        super().__init__()
        pad = dilation
        self.conv1 = nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=pad, dilation=dilation, bias=False)
        self.bn1 = _make_norm(norm, out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1, bias=False)
        self.bn2 = _make_norm(norm, out_ch)
        self.act = nn.ReLU(inplace=True)
        self.se = SEBlock(out_ch, reduction=8)

        if in_ch != out_ch:
            self.skip = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, kernel_size=1, bias=False),
                _make_norm(norm, out_ch),
            )
        else:
            self.skip = nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = self.skip(x)
        out = self.act(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out = self.se(out)
        out = self.act(out + identity)
        return out


class MultiScaleBottleneck(nn.Module):
    def __init__(self, channels: int, norm: str = "batch"):
        super().__init__()
        self.b1 = ResidualConvBlock(channels, channels, dilation=1, norm=norm)
        self.b2 = ResidualConvBlock(channels, channels, dilation=2, norm=norm)
        self.b3 = ResidualConvBlock(channels, channels, dilation=3, norm=norm)
        self.fuse = nn.Sequential(
            nn.Conv2d(channels * 3, channels, kernel_size=1, bias=False),
            _make_norm(norm, channels),
            nn.ReLU(inplace=True),
            nn.Dropout2d(p=0.15),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y1 = self.b1(x)
        y2 = self.b2(x)
        y3 = self.b3(x)
        return self.fuse(torch.cat([y1, y2, y3], dim=1))


class TemporalUNet(nn.Module):
    """Accuracy-oriented temporal U-Net for 8GB VRAM training."""

    def __init__(self, in_channels: int, num_classes: int, base_channels: int = 32, norm: str = "batch"):
        super().__init__()
        c = base_channels

        self.enc1 = ResidualConvBlock(in_channels, c, norm=norm)
        self.pool1 = nn.MaxPool2d(2)
        self.enc2 = ResidualConvBlock(c, c * 2, norm=norm)
        self.pool2 = nn.MaxPool2d(2)
        self.enc3 = ResidualConvBlock(c * 2, c * 4, norm=norm)
        self.pool3 = nn.MaxPool2d(2)

        self.bridge_in = ResidualConvBlock(c * 4, c * 8, norm=norm)
        self.bridge_ms = MultiScaleBottleneck(c * 8, norm=norm)

        self.up3 = nn.ConvTranspose2d(c * 8, c * 4, kernel_size=2, stride=2)
        self.dec3 = ResidualConvBlock(c * 8, c * 4, norm=norm)
        self.up2 = nn.ConvTranspose2d(c * 4, c * 2, kernel_size=2, stride=2)
        self.dec2 = ResidualConvBlock(c * 4, c * 2, norm=norm)
        self.up1 = nn.ConvTranspose2d(c * 2, c, kernel_size=2, stride=2)
        self.dec1 = ResidualConvBlock(c * 2, c, norm=norm)

        self.class_head = nn.Sequential(
            nn.Conv2d(c, c, kernel_size=3, padding=1, bias=False),
            _make_norm(norm, c),
            nn.ReLU(inplace=True),
            nn.Conv2d(c, num_classes, kernel_size=1),
        )
        self.conf_head = nn.Sequential(
            nn.Conv2d(c, c // 2, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(c // 2, 1, kernel_size=1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool1(e1))
        e3 = self.enc3(self.pool2(e2))

        b = self.bridge_in(self.pool3(e3))
        b = self.bridge_ms(b)

        d3 = self.up3(b)
        d3 = torch.cat([d3, e3], dim=1)
        d3 = self.dec3(d3)

        d2 = self.up2(d3)
        d2 = torch.cat([d2, e2], dim=1)
        d2 = self.dec2(d2)

        d1 = self.up1(d2)
        d1 = torch.cat([d1, e1], dim=1)
        d1 = self.dec1(d1)

        logits = self.class_head(d1)
        confidence = self.conf_head(d1)
        return logits, confidence
