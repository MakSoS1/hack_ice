from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.palette import load_palette
from app.scene_index import SceneIndex
from ml.model import TemporalUNet


def build_features(scene_index: SceneIndex, palette, scene_id: str, history_steps: int, crop_size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rec = scene_index.get(scene_id)

    bgr = cv2.imread(str(rec.iceclass_path), cv2.IMREAD_UNCHANGED)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    cur_cls = palette.rgb_to_class_ids(rgb)

    gap = scene_index.read_gap_mask(scene_id)
    gap = cv2.resize(gap.astype(np.uint8), (cur_cls.shape[1], cur_cls.shape[0]), interpolation=cv2.INTER_NEAREST)

    history = scene_index.get_history(scene_id, history_steps)
    hist_cls = []
    for h in history:
        hbgr = cv2.imread(str(h.iceclass_path), cv2.IMREAD_UNCHANGED)
        hrgb = cv2.cvtColor(hbgr, cv2.COLOR_BGR2RGB)
        hc = palette.rgb_to_class_ids(hrgb)
        hc = cv2.resize(hc.astype(np.uint8), (cur_cls.shape[1], cur_cls.shape[0]), interpolation=cv2.INTER_NEAREST)
        hist_cls.append(hc)
    while len(hist_cls) < history_steps:
        hist_cls.append(cur_cls)

    observed = cur_cls.copy()
    observed[gap == 1] = palette.unknown_id

    cur_small = cv2.resize(observed.astype(np.uint8), (crop_size, crop_size), interpolation=cv2.INTER_NEAREST)
    gap_small = cv2.resize(gap.astype(np.uint8), (crop_size, crop_size), interpolation=cv2.INTER_NEAREST)
    hist_small = [cv2.resize(h.astype(np.uint8), (crop_size, crop_size), interpolation=cv2.INTER_NEAREST) for h in hist_cls]

    max_class = max(1.0, float(np.max(palette.class_ids)))
    chans = [cur_small.astype(np.float32) / max_class]
    chans.extend([h.astype(np.float32) / max_class for h in hist_small])
    chans.append((gap_small == 0).astype(np.float32))
    month = rec.acquisition_start.month
    angle = 2.0 * np.pi * (float(month - 1) / 12.0)
    chans.append(np.full(cur_small.shape, np.sin(angle), dtype=np.float32))
    chans.append(np.full(cur_small.shape, np.cos(angle), dtype=np.float32))
    x = np.stack(chans, axis=0)
    return x, cur_small, gap_small


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-id", required=True)
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "backend" / "checkpoints" / "mvp_unet.pt")
    parser.add_argument("--output", type=Path, default=ROOT / "storage" / "infer_preview.npz")
    parser.add_argument("--history-steps", type=int, default=2)
    parser.add_argument("--crop-size", type=int, default=512)
    parser.add_argument("--ice-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass"))
    parser.add_argument("--comp-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite"))
    parser.add_argument("--palette", type=Path, default=ROOT / "configs" / "ice_palette.json")
    args = parser.parse_args()

    scene_index = SceneIndex(args.ice_dir, args.comp_dir)
    palette = load_palette(args.palette)

    x, current, gap = build_features(scene_index, palette, args.scene_id, args.history_steps, args.crop_size)

    ckpt = torch.load(args.checkpoint, map_location="cpu")
    in_channels = int(ckpt.get("in_channels", args.history_steps + 4))
    base_channels = int(ckpt.get("base_channels", 32))
    model = TemporalUNet(in_channels=in_channels, num_classes=len(palette.class_ids), base_channels=base_channels)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    with torch.no_grad():
        logits, conf = model(torch.from_numpy(x).unsqueeze(0))
        pred_idx = torch.argmax(logits, dim=1).squeeze(0).cpu().numpy().astype(np.int64)
        pred = palette.class_ids[pred_idx].astype(np.uint8)
        conf = conf.squeeze(0).squeeze(0).cpu().numpy().astype(np.float32)

    recon = current.copy()
    recon[gap == 1] = pred[gap == 1]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, current=current, gap=gap, pred=pred, recon=recon, confidence=conf)
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
