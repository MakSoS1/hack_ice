from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class IceClassPalette:
    class_ids: np.ndarray
    class_names: list[str]
    class_rgbs: np.ndarray  # (K,3)
    class_costs: np.ndarray  # (K,)
    unknown_id: int
    unknown_rgb: np.ndarray
    unknown_cost: float

    def rgb_to_class_ids(self, rgb: np.ndarray) -> np.ndarray:
        if rgb.ndim != 3 or rgb.shape[-1] != 3:
            raise ValueError("Expected RGB image with shape (H, W, 3)")

        flat = rgb.reshape(-1, 3).astype(np.uint8)
        unique, inv = np.unique(flat, axis=0, return_inverse=True)

        mapping: dict[tuple[int, int, int], int] = {
            tuple(map(int, color.tolist())): int(class_id)
            for color, class_id in zip(self.class_rgbs, self.class_ids, strict=True)
        }

        out_unique = np.empty(unique.shape[0], dtype=np.uint8)
        for i, color in enumerate(unique):
            key = tuple(map(int, color.tolist()))
            if key in mapping:
                out_unique[i] = mapping[key]
                continue
            # Fallback: nearest palette color by Euclidean distance in RGB space.
            d = np.sum((self.class_rgbs.astype(np.float32) - color.astype(np.float32)) ** 2, axis=1)
            out_unique[i] = self.class_ids[int(np.argmin(d))]

        out = out_unique[inv].reshape(rgb.shape[:2])
        return out

    def class_ids_to_rgb(self, class_ids: np.ndarray) -> np.ndarray:
        if class_ids.ndim != 2:
            raise ValueError("Expected class map with shape (H, W)")

        h, w = class_ids.shape
        out = np.empty((h, w, 3), dtype=np.uint8)
        out[:] = self.unknown_rgb

        for class_id, color in zip(self.class_ids, self.class_rgbs, strict=True):
            out[class_ids == class_id] = color

        return out

    def class_cost_grid(self, class_ids: np.ndarray) -> np.ndarray:
        out = np.full(class_ids.shape, fill_value=self.unknown_cost, dtype=np.float32)
        for class_id, cost in zip(self.class_ids, self.class_costs, strict=True):
            out[class_ids == class_id] = float(cost)
        return out


def load_palette(config_path: Path) -> IceClassPalette:
    raw = json.loads(config_path.read_text(encoding="utf-8"))

    classes = raw["classes"]
    class_ids = np.array([int(c["id"]) for c in classes], dtype=np.uint8)
    class_names = [str(c["name"]) for c in classes]
    class_rgbs = np.array([c["rgb"] for c in classes], dtype=np.uint8)
    class_costs = np.array([float(c["cost"]) for c in classes], dtype=np.float32)

    unknown = raw.get("unknown_class", {"id": 255, "rgb": [0, 0, 0], "cost": 9.0})

    return IceClassPalette(
        class_ids=class_ids,
        class_names=class_names,
        class_rgbs=class_rgbs,
        class_costs=class_costs,
        unknown_id=int(unknown.get("id", 255)),
        unknown_rgb=np.array(unknown.get("rgb", [0, 0, 0]), dtype=np.uint8),
        unknown_cost=float(unknown.get("cost", 9.0)),
    )
