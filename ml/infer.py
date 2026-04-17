from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.palette import load_palette
from app.scene_index import SceneIndex
from ml.predictor import TemporalUNetPredictor


def _read_ice_rgb(path: Path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise RuntimeError(f"Failed to read {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-id", required=True)
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "backend" / "checkpoints" / "mvp_unet.pt")
    parser.add_argument("--output", type=Path, default=ROOT / "storage" / "infer_preview.npz")
    parser.add_argument("--history-steps", type=int, default=2)
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--tile-overlap", type=int, default=64)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--ice-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass"))
    parser.add_argument("--comp-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite"))
    parser.add_argument("--palette", type=Path, default=ROOT / "configs" / "ice_palette.json")
    args = parser.parse_args()

    scene_index = SceneIndex(args.ice_dir, args.comp_dir)
    palette = load_palette(args.palette)
    rec = scene_index.get(args.scene_id)
    cur_rgb = _read_ice_rgb(rec.iceclass_path)
    current = palette.rgb_to_class_ids(cur_rgb)
    gap = scene_index.read_gap_mask(args.scene_id)
    gap = cv2.resize(gap.astype(np.uint8), (current.shape[1], current.shape[0]), interpolation=cv2.INTER_NEAREST)
    observed = current.copy()
    observed[gap == 1] = palette.unknown_id

    hist = scene_index.get_history(args.scene_id, args.history_steps)
    hist_cls: list[np.ndarray] = []
    for hrec in hist:
        hrgb = _read_ice_rgb(hrec.iceclass_path)
        hcls = palette.rgb_to_class_ids(hrgb)
        hcls = cv2.resize(hcls.astype(np.uint8), (current.shape[1], current.shape[0]), interpolation=cv2.INTER_NEAREST)
        hist_cls.append(hcls)
    while len(hist_cls) < args.history_steps:
        hist_cls.append(current)

    predictor = TemporalUNetPredictor(
        checkpoint=args.checkpoint,
        palette=palette,
        history_steps=args.history_steps,
        tile_size=args.tile_size,
        tile_overlap=args.tile_overlap,
        device=args.device,
    )
    recon, conf = predictor.predict(
        month=rec.acquisition_start.month,
        observed=observed,
        gap=gap,
        history_cls=hist_cls,
    )

    pred = recon.copy()
    pred[gap == 0] = observed[gap == 0]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, current=current, gap=gap, pred=pred, recon=recon, confidence=conf)
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
