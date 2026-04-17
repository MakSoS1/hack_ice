from __future__ import annotations

import random
from dataclasses import dataclass

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from app.palette import IceClassPalette
from app.scene_index import SceneIndex


@dataclass(frozen=True)
class SceneSample:
    x: torch.Tensor
    y: torch.Tensor
    gap_mask: torch.Tensor
    confidence_target: torch.Tensor


class SceneTemporalDataset(Dataset[SceneSample]):
    def __init__(
        self,
        *,
        scene_index: SceneIndex,
        palette: IceClassPalette,
        scene_ids: list[str],
        history_steps: int = 2,
        crop_size: int = 512,
        random_crop: bool = True,
        gap_focus_prob: float = 0.8,
        augment: bool = False,
        seed: int = 42,
    ):
        self.scene_index = scene_index
        self.palette = palette
        self.scene_ids = scene_ids
        self.history_steps = history_steps
        self.crop_size = crop_size
        self.random_crop = random_crop
        self.gap_focus_prob = float(np.clip(gap_focus_prob, 0.0, 1.0))
        self.augment = augment

        self.max_class = max(1.0, float(np.max(self.palette.class_ids)))
        self.rng = random.Random(seed)
        self.id_to_index_lut = np.full(256, 0, dtype=np.uint8)
        for i, cid in enumerate(self.palette.class_ids.tolist()):
            self.id_to_index_lut[int(cid)] = int(i)

    def __len__(self) -> int:
        return len(self.scene_ids)

    def __getitem__(self, idx: int) -> SceneSample:
        scene_id = self.scene_ids[idx]
        rec = self.scene_index.get(scene_id)

        cur_rgb = self._read_ice(rec.iceclass_path)
        cur_cls = self.palette.rgb_to_class_ids(cur_rgb)
        cur_gap = self._resize(self.scene_index.read_gap_mask(scene_id), cur_cls.shape)

        history_cls: list[np.ndarray] = []
        history_gap: list[np.ndarray] = []
        history = self.scene_index.get_history(scene_id, self.history_steps)
        for hrec in history:
            hrgb = self._read_ice(hrec.iceclass_path)
            hcls = self.palette.rgb_to_class_ids(hrgb)
            hcls = self._resize(hcls, cur_cls.shape)
            hgap = self._resize(self.scene_index.read_gap_mask(hrec.scene_id), cur_cls.shape)
            history_cls.append(hcls)
            history_gap.append(hgap)

        while len(history_cls) < self.history_steps:
            history_cls.append(cur_cls)
            history_gap.append(cur_gap)

        current_observed = cur_cls.copy()
        current_observed[cur_gap == 1] = self.palette.unknown_id

        # Crop with preference for masked areas to optimize accuracy where it matters.
        cur_crop, target_crop, gap_crop, hist_cls_crop, hist_gap_crop = self._crop_pack(
            current_observed=current_observed,
            target=cur_cls,
            gap=cur_gap,
            hist_cls=history_cls,
            hist_gap=history_gap,
        )

        if self.augment:
            cur_crop, target_crop, gap_crop, hist_cls_crop, hist_gap_crop = self._augment_pack(
                cur_crop,
                target_crop,
                gap_crop,
                hist_cls_crop,
                hist_gap_crop,
            )

        # Seasonal context as continuous cyclic embedding.
        month = rec.acquisition_start.month
        angle = 2.0 * np.pi * (float(month - 1) / 12.0)
        month_sin = np.full(cur_crop.shape, fill_value=np.sin(angle), dtype=np.float32)
        month_cos = np.full(cur_crop.shape, fill_value=np.cos(angle), dtype=np.float32)

        observed_mask = (gap_crop == 0).astype(np.float32)
        channels = [cur_crop.astype(np.float32) / self.max_class]
        channels.extend([h.astype(np.float32) / self.max_class for h in hist_cls_crop])
        channels.append(observed_mask)
        channels.append(month_sin)
        channels.append(month_cos)
        x = np.stack(channels, axis=0)

        # Confidence target:
        # - observed pixels: 1.0
        # - masked with temporal support: 0.8
        # - masked without support: 0.55
        hist_support = np.zeros_like(gap_crop, dtype=np.uint8)
        for hgap in hist_gap_crop:
            hist_support |= (hgap == 0).astype(np.uint8)
        conf_target = np.where(gap_crop == 0, 1.0, np.where(hist_support == 1, 0.8, 0.55)).astype(np.float32)

        target_idx = self.id_to_index_lut[target_crop]

        return SceneSample(
            x=torch.from_numpy(x),
            y=torch.from_numpy(target_idx.astype(np.int64)),
            gap_mask=torch.from_numpy(gap_crop.astype(np.float32)),
            confidence_target=torch.from_numpy(conf_target).unsqueeze(0),
        )

    def _crop_pack(
        self,
        *,
        current_observed: np.ndarray,
        target: np.ndarray,
        gap: np.ndarray,
        hist_cls: list[np.ndarray],
        hist_gap: list[np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[np.ndarray], list[np.ndarray]]:
        h, w = target.shape
        cs = self.crop_size

        # Fallback to resize when scene is smaller than crop.
        if h < cs or w < cs:
            cur = self._resize(current_observed, (cs, cs))
            tgt = self._resize(target, (cs, cs))
            g = self._resize(gap, (cs, cs))
            hc = [self._resize(x, (cs, cs)) for x in hist_cls]
            hg = [self._resize(x, (cs, cs)) for x in hist_gap]
            return cur, tgt, g, hc, hg

        if not self.random_crop:
            y0 = (h - cs) // 2
            x0 = (w - cs) // 2
            return self._slice_pack(y0, x0, cs, current_observed, target, gap, hist_cls, hist_gap)

        y0, x0 = self._sample_crop_origin(gap, cs)
        return self._slice_pack(y0, x0, cs, current_observed, target, gap, hist_cls, hist_gap)

    def _sample_crop_origin(self, gap: np.ndarray, crop_size: int) -> tuple[int, int]:
        h, w = gap.shape
        max_y0 = h - crop_size
        max_x0 = w - crop_size

        gap_yx = np.argwhere(gap == 1)
        if gap_yx.size > 0 and self.rng.random() < self.gap_focus_prob:
            gy, gx = gap_yx[self.rng.randrange(len(gap_yx))]
            y0 = int(gy) - crop_size // 2
            x0 = int(gx) - crop_size // 2
            y0 = max(0, min(max_y0, y0))
            x0 = max(0, min(max_x0, x0))
            return y0, x0

        y0 = self.rng.randint(0, max_y0)
        x0 = self.rng.randint(0, max_x0)
        return y0, x0

    @staticmethod
    def _slice_pack(
        y0: int,
        x0: int,
        cs: int,
        current_observed: np.ndarray,
        target: np.ndarray,
        gap: np.ndarray,
        hist_cls: list[np.ndarray],
        hist_gap: list[np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[np.ndarray], list[np.ndarray]]:
        y1, x1 = y0 + cs, x0 + cs
        cur = current_observed[y0:y1, x0:x1]
        tgt = target[y0:y1, x0:x1]
        g = gap[y0:y1, x0:x1]
        hc = [x[y0:y1, x0:x1] for x in hist_cls]
        hg = [x[y0:y1, x0:x1] for x in hist_gap]
        return cur, tgt, g, hc, hg

    def _augment_pack(
        self,
        cur: np.ndarray,
        tgt: np.ndarray,
        gap: np.ndarray,
        hist_cls: list[np.ndarray],
        hist_gap: list[np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[np.ndarray], list[np.ndarray]]:
        # Horizontal flip
        if self.rng.random() < 0.5:
            cur = np.flip(cur, axis=1)
            tgt = np.flip(tgt, axis=1)
            gap = np.flip(gap, axis=1)
            hist_cls = [np.flip(x, axis=1) for x in hist_cls]
            hist_gap = [np.flip(x, axis=1) for x in hist_gap]

        # Vertical flip
        if self.rng.random() < 0.5:
            cur = np.flip(cur, axis=0)
            tgt = np.flip(tgt, axis=0)
            gap = np.flip(gap, axis=0)
            hist_cls = [np.flip(x, axis=0) for x in hist_cls]
            hist_gap = [np.flip(x, axis=0) for x in hist_gap]

        # 90-degree rotation
        k = self.rng.randrange(4)
        if k:
            cur = np.rot90(cur, k=k)
            tgt = np.rot90(tgt, k=k)
            gap = np.rot90(gap, k=k)
            hist_cls = [np.rot90(x, k=k) for x in hist_cls]
            hist_gap = [np.rot90(x, k=k) for x in hist_gap]

        return (
            np.ascontiguousarray(cur),
            np.ascontiguousarray(tgt),
            np.ascontiguousarray(gap),
            [np.ascontiguousarray(x) for x in hist_cls],
            [np.ascontiguousarray(x) for x in hist_gap],
        )

    @staticmethod
    def _read_ice(path) -> np.ndarray:
        bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if bgr is None:
            raise RuntimeError(f"Failed to read {path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return rgb

    @staticmethod
    def _resize(arr: np.ndarray, shape_hw: tuple[int, int]) -> np.ndarray:
        h, w = int(shape_hw[0]), int(shape_hw[1])
        out = cv2.resize(arr.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
        return out
