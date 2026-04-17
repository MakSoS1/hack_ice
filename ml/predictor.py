from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from app.palette import IceClassPalette
from ml.model import TemporalUNet


def _tile_starts(length: int, tile: int, overlap: int) -> list[int]:
    if length <= tile:
        return [0]
    stride = max(1, tile - 2 * max(0, overlap))
    starts = [0]
    while True:
        nxt = starts[-1] + stride
        if nxt + tile >= length:
            last = length - tile
            if last != starts[-1]:
                starts.append(last)
            break
        starts.append(nxt)
    return starts


def _extract_tile_u8(arr: np.ndarray, y0: int, x0: int, tile: int, pad_value: int) -> tuple[np.ndarray, int, int]:
    h, w = arr.shape
    y1 = min(h, y0 + tile)
    x1 = min(w, x0 + tile)
    out = np.full((tile, tile), fill_value=np.uint8(pad_value), dtype=np.uint8)
    valid_h = y1 - y0
    valid_w = x1 - x0
    out[:valid_h, :valid_w] = arr[y0:y1, x0:x1].astype(np.uint8)
    return out, valid_h, valid_w


class TemporalUNetPredictor:
    def __init__(
        self,
        *,
        checkpoint: Path,
        palette: IceClassPalette,
        history_steps: int | None = None,
        tile_size: int = 512,
        tile_overlap: int = 64,
        device: str = "auto",
    ):
        ckpt = torch.load(checkpoint, map_location="cpu")
        in_channels = int(ckpt.get("in_channels", (history_steps or 2) + 4))
        self.history_steps = max(1, in_channels - 4)
        base_channels = int(ckpt.get("base_channels", 32))
        norm = str(ckpt.get("norm", "batch"))

        model = TemporalUNet(
            in_channels=in_channels,
            num_classes=len(palette.class_ids),
            base_channels=base_channels,
            norm=norm,
        )
        model.load_state_dict(ckpt["model_state"], strict=False)

        if device == "auto":
            use_cuda = torch.cuda.is_available()
            self.device = torch.device("cuda" if use_cuda else "cpu")
        elif device == "cuda" and torch.cuda.is_available():
            self.device = torch.device("cuda")
        else:
            self.device = torch.device("cpu")

        self.model = model.to(self.device).eval()
        self.palette = palette
        self.max_class = max(1.0, float(np.max(self.palette.class_ids)))
        self.tile_size = max(128, int(tile_size))
        self.tile_overlap = max(0, min(int(tile_overlap), self.tile_size // 4))

    def _build_input(
        self,
        *,
        observed: np.ndarray,
        gap: np.ndarray,
        history_cls: list[np.ndarray],
        month: int,
    ) -> torch.Tensor:
        month = int(np.clip(month, 1, 12))
        angle = 2.0 * np.pi * (float(month - 1) / 12.0)

        hist = [h.astype(np.float32) / self.max_class for h in history_cls[: self.history_steps]]
        while len(hist) < self.history_steps:
            hist.append(observed.astype(np.float32) / self.max_class)

        ch = [observed.astype(np.float32) / self.max_class]
        ch.extend(hist)
        ch.append((gap == 0).astype(np.float32))
        ch.append(np.full(observed.shape, np.sin(angle), dtype=np.float32))
        ch.append(np.full(observed.shape, np.cos(angle), dtype=np.float32))
        x = np.stack(ch, axis=0)
        return torch.from_numpy(x).unsqueeze(0).to(self.device)

    def predict(
        self,
        *,
        month: int,
        observed: np.ndarray,
        gap: np.ndarray,
        history_cls: list[np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray]:
        if observed.shape != gap.shape:
            raise ValueError("observed and gap must have the same shape")

        h, w = observed.shape
        y_starts = _tile_starts(h, self.tile_size, self.tile_overlap)
        x_starts = _tile_starts(w, self.tile_size, self.tile_overlap)

        reconstructed = observed.copy()
        confidence = np.where(gap == 0, 1.0, 0.0).astype(np.float32)

        for y0 in y_starts:
            for x0 in x_starts:
                cur_tile, valid_h, valid_w = _extract_tile_u8(observed, y0, x0, self.tile_size, int(self.palette.unknown_id))
                gap_tile, _, _ = _extract_tile_u8(gap, y0, x0, self.tile_size, 0)
                hist_tiles = [_extract_tile_u8(hc, y0, x0, self.tile_size, int(self.palette.unknown_id))[0] for hc in history_cls]

                x = self._build_input(
                    observed=cur_tile,
                    gap=gap_tile,
                    history_cls=hist_tiles,
                    month=month,
                )
                with torch.no_grad():
                    logits, conf = self.model(x)
                    pred_idx = torch.argmax(logits, dim=1).squeeze(0).cpu().numpy().astype(np.int64)
                    conf_map = conf.squeeze(0).squeeze(0).cpu().numpy().astype(np.float32)
                pred_ids = self.palette.class_ids[pred_idx].astype(np.uint8)

                top = 0 if y0 == 0 else self.tile_overlap
                left = 0 if x0 == 0 else self.tile_overlap
                bottom = valid_h if (y0 + valid_h) >= h else max(top + 1, valid_h - self.tile_overlap)
                right = valid_w if (x0 + valid_w) >= w else max(left + 1, valid_w - self.tile_overlap)
                if bottom <= top:
                    top, bottom = 0, valid_h
                if right <= left:
                    left, right = 0, valid_w

                oy0, oy1 = y0 + top, y0 + bottom
                ox0, ox1 = x0 + left, x0 + right
                local_pred = pred_ids[top:bottom, left:right]
                local_conf = conf_map[top:bottom, left:right]
                local_gap = gap[oy0:oy1, ox0:ox1] == 1

                if np.any(local_gap):
                    dst_cls = reconstructed[oy0:oy1, ox0:ox1]
                    dst_cls[local_gap] = local_pred[local_gap]
                    reconstructed[oy0:oy1, ox0:ox1] = dst_cls

                    dst_conf = confidence[oy0:oy1, ox0:ox1]
                    dst_conf[local_gap] = np.clip(local_conf[local_gap], 0.0, 1.0)
                    confidence[oy0:oy1, ox0:ox1] = dst_conf

        return reconstructed.astype(np.uint8), np.clip(confidence, 0.0, 1.0).astype(np.float32)
