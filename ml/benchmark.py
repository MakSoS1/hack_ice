from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.palette import IceClassPalette, load_palette
from app.scene_index import SceneIndex
from ml.metrics import evaluate_segmentation
from ml.model import TemporalUNet


def _read_ice_rgb(path: Path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise RuntimeError(f"Failed to read {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _resize_nn(arr: np.ndarray, shape_hw: tuple[int, int]) -> np.ndarray:
    h, w = shape_hw
    return cv2.resize(arr.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)


def _temporal_fill(
    observed: np.ndarray,
    gap: np.ndarray,
    history_cls: list[np.ndarray],
    history_gap: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    pred = observed.copy()
    conf = np.where(gap == 0, 1.0, 0.0).astype(np.float32)
    for i, (hc, hg) in enumerate(zip(history_cls, history_gap, strict=False)):
        m = (gap == 1) & (conf == 0.0) & (hg == 0)
        if np.any(m):
            pred[m] = hc[m]
            conf[m] = max(0.6, 0.9 - 0.12 * i)

    rem = (gap == 1) & (conf == 0.0)
    if np.any(rem):
        vals = observed[gap == 0]
        mode_cls = int(np.bincount(vals.reshape(-1)).argmax()) if vals.size else int(np.bincount(observed.reshape(-1)).argmax())
        pred[rem] = mode_cls
        conf[rem] = 0.55
    return pred, conf


def _persistence_t1(
    observed: np.ndarray,
    gap: np.ndarray,
    history_cls: list[np.ndarray],
    history_gap: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    pred = observed.copy()
    conf = np.where(gap == 0, 1.0, 0.0).astype(np.float32)
    if history_cls:
        m = (gap == 1) & (history_gap[0] == 0)
        pred[m] = history_cls[0][m]
        conf[m] = 0.82
    rem = (gap == 1) & (conf == 0.0)
    if np.any(rem):
        vals = observed[gap == 0]
        mode_cls = int(np.bincount(vals.reshape(-1)).argmax()) if vals.size else int(np.bincount(observed.reshape(-1)).argmax())
        pred[rem] = mode_cls
        conf[rem] = 0.50
    return pred, conf


class CkptInfer:
    def __init__(self, checkpoint: Path, history_steps: int, palette: IceClassPalette, crop_size: int):
        ckpt = torch.load(checkpoint, map_location="cpu")
        in_channels = int(ckpt.get("in_channels", history_steps + 4))
        base_channels = int(ckpt.get("base_channels", 32))
        self.model = TemporalUNet(in_channels=in_channels, num_classes=len(palette.class_ids), base_channels=base_channels)
        self.model.load_state_dict(ckpt["model_state"])
        self.model.eval()
        self.palette = palette
        self.history_steps = history_steps
        self.crop_size = crop_size
        self.max_class = max(1.0, float(np.max(palette.class_ids)))

    def predict(
        self,
        *,
        scene_id: str,
        month: int,
        observed: np.ndarray,
        gap: np.ndarray,
        history_cls: list[np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray]:
        h, w = observed.shape
        cur = _resize_nn(observed, (self.crop_size, self.crop_size))
        gap_s = _resize_nn(gap, (self.crop_size, self.crop_size))

        hist_small: list[np.ndarray] = []
        for hc in history_cls:
            hist_small.append(_resize_nn(hc, (self.crop_size, self.crop_size)))
        while len(hist_small) < self.history_steps:
            hist_small.append(cur)

        ang = 2.0 * np.pi * (float(month - 1) / 12.0)
        ch = [cur.astype(np.float32) / self.max_class]
        ch.extend([x.astype(np.float32) / self.max_class for x in hist_small[: self.history_steps]])
        ch.append((gap_s == 0).astype(np.float32))
        ch.append(np.full(cur.shape, np.sin(ang), dtype=np.float32))
        ch.append(np.full(cur.shape, np.cos(ang), dtype=np.float32))
        x = torch.from_numpy(np.stack(ch, axis=0)).unsqueeze(0)

        with torch.no_grad():
            logits, conf = self.model(x)
            pred_idx = torch.argmax(logits, dim=1).squeeze(0).cpu().numpy().astype(np.int64)
            conf_map = conf.squeeze(0).squeeze(0).cpu().numpy().astype(np.float32)

        pred_ids = self.palette.class_ids[pred_idx].astype(np.uint8)
        pred_up = cv2.resize(pred_ids, (w, h), interpolation=cv2.INTER_NEAREST)
        conf_up = cv2.resize(conf_map.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)

        out = observed.copy()
        out[gap == 1] = pred_up[gap == 1]
        return out, np.clip(conf_up, 0.0, 1.0)


def _load_yolo_pred(scene_id: str, yolo_dir: Path, shape_hw: tuple[int, int]) -> tuple[np.ndarray, np.ndarray] | None:
    h, w = shape_hw
    npy = yolo_dir / f"{scene_id}.npy"
    npz = yolo_dir / f"{scene_id}.npz"
    png = yolo_dir / f"{scene_id}.png"

    pred = None
    conf = None
    if npy.exists():
        pred = np.load(npy)
    elif npz.exists():
        z = np.load(npz)
        if "pred" in z:
            pred = z["pred"]
        elif "classes" in z:
            pred = z["classes"]
        if "confidence" in z:
            conf = z["confidence"]
    elif png.exists():
        im = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
        if im is not None:
            if im.ndim == 3:
                pred = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
            else:
                pred = im

    if pred is None:
        return None
    pred = pred.astype(np.uint8)
    if pred.shape != (h, w):
        pred = cv2.resize(pred, (w, h), interpolation=cv2.INTER_NEAREST)
    if conf is None:
        conf = np.full((h, w), 0.5, dtype=np.float32)
    else:
        conf = conf.astype(np.float32)
        if conf.shape != (h, w):
            conf = cv2.resize(conf, (w, h), interpolation=cv2.INTER_LINEAR)
    return pred, np.clip(conf, 0.0, 1.0)


def _aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    keys = rows[0].keys()
    out = {}
    for k in keys:
        out[k] = float(np.mean([float(r[k]) for r in rows]))
    return out


def _gap_bin(v: float) -> str:
    p = v * 100.0
    if p < 20:
        return "lt20"
    if p < 35:
        return "20_35"
    if p < 50:
        return "35_50"
    return "ge50"


def run_benchmark(
    *,
    ice_dir: Path,
    comp_dir: Path,
    palette_path: Path,
    history_steps: int,
    checkpoint: Path | None,
    yolo_pred_dir: Path | None,
    max_scenes: int,
    seed: int,
    crop_size: int,
    output_json: Path,
    output_md: Path,
    yolo_summary_json: Path | None,
) -> dict:
    rng = random.Random(seed)
    index = SceneIndex(ice_dir, comp_dir)
    palette = load_palette(palette_path)

    all_ids = index.list_scene_ids()
    valid_ids = all_ids[history_steps:]
    if not valid_ids:
        raise RuntimeError("No scenes with required history_steps")

    if max_scenes < len(valid_ids):
        rng.shuffle(valid_ids)
        eval_ids = valid_ids[:max_scenes]
    else:
        eval_ids = valid_ids

    infer = None
    if checkpoint and checkpoint.exists():
        infer = CkptInfer(checkpoint=checkpoint, history_steps=history_steps, palette=palette, crop_size=crop_size)

    method_rows: dict[str, list[dict[str, float]]] = defaultdict(list)
    by_gap: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))
    by_month: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))

    for sid in eval_ids:
        rec = index.get(sid)
        cur_rgb = _read_ice_rgb(rec.iceclass_path)
        gt = palette.rgb_to_class_ids(cur_rgb)
        gap = _resize_nn(index.read_gap_mask(sid), gt.shape)
        observed = gt.copy()
        observed[gap == 1] = palette.unknown_id

        hist = index.get_history(sid, history_steps)
        hist_cls: list[np.ndarray] = []
        hist_gap: list[np.ndarray] = []
        for hrec in hist:
            hrgb = _read_ice_rgb(hrec.iceclass_path)
            hcls = _resize_nn(palette.rgb_to_class_ids(hrgb), gt.shape)
            hgap = _resize_nn(index.read_gap_mask(hrec.scene_id), gt.shape)
            hist_cls.append(hcls)
            hist_gap.append(hgap)
        while len(hist_cls) < history_steps:
            hist_cls.append(gt)
            hist_gap.append(gap)

        preds: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        preds["persistence_t1"] = _persistence_t1(observed, gap, hist_cls, hist_gap)
        preds["temporal_fill"] = _temporal_fill(observed, gap, hist_cls, hist_gap)
        if infer is not None:
            preds["temporal_unet"] = infer.predict(
                scene_id=sid,
                month=rec.acquisition_start.month,
                observed=observed,
                gap=gap,
                history_cls=hist_cls,
            )
        if yolo_pred_dir is not None:
            yp = _load_yolo_pred(sid, yolo_pred_dir, gt.shape)
            if yp is not None:
                y_pred, y_conf = yp
                out = observed.copy()
                out[gap == 1] = y_pred[gap == 1]
                preds["yolo_external"] = (out, y_conf)

        gbin = _gap_bin(float(np.mean(gap)))
        mbin = str(rec.acquisition_start.month)
        for method, (pred, conf) in preds.items():
            m = evaluate_segmentation(
                y_true=gt,
                y_pred=pred,
                gap_mask=gap,
                class_ids=palette.class_ids,
                confidence=conf,
            )
            row = {
                "masked_accuracy": m.masked_accuracy,
                "masked_macro_f1": m.masked_macro_f1,
                "masked_miou": m.masked_miou,
                "masked_edge_f1": m.masked_edge_f1,
                "confidence_brier": m.confidence_brier,
                "confidence_ece": m.confidence_ece,
                "recovered_ratio": m.recovered_ratio,
            }
            method_rows[method].append(row)
            by_gap[method][gbin].append(row)
            by_month[method][mbin].append(row)

    methods = {k: {"count": len(v), "avg": _aggregate(v)} for k, v in method_rows.items()}
    ranking = sorted(
        [{"method": k, "masked_miou": v["avg"].get("masked_miou", 0.0)} for k, v in methods.items()],
        key=lambda x: x["masked_miou"],
        reverse=True,
    )

    gates = {
        "model_vs_persistence_miou_delta": None,
        "model_vs_yolo_status": "not_verified",
        "model_vs_yolo_miou_delta": None,
    }
    if "temporal_unet" in methods and "persistence_t1" in methods:
        gates["model_vs_persistence_miou_delta"] = float(
            methods["temporal_unet"]["avg"]["masked_miou"] - methods["persistence_t1"]["avg"]["masked_miou"]
        )
    if "temporal_unet" in methods and "yolo_external" in methods:
        delta = float(methods["temporal_unet"]["avg"]["masked_miou"] - methods["yolo_external"]["avg"]["masked_miou"])
        gates["model_vs_yolo_miou_delta"] = delta
        gates["model_vs_yolo_status"] = "pass" if delta > 0.0 else "fail"
    elif yolo_summary_json and yolo_summary_json.exists() and "temporal_unet" in methods:
        yolo_ref = json.loads(yolo_summary_json.read_text(encoding="utf-8"))
        ref = float(yolo_ref.get("masked_miou", 0.0))
        delta = float(methods["temporal_unet"]["avg"]["masked_miou"] - ref)
        gates["model_vs_yolo_miou_delta"] = delta
        gates["model_vs_yolo_status"] = "pass" if delta > 0.0 else "fail"

    out = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "config": {
            "history_steps": history_steps,
            "max_scenes": len(eval_ids),
            "seed": seed,
            "checkpoint": str(checkpoint) if checkpoint else None,
            "yolo_pred_dir": str(yolo_pred_dir) if yolo_pred_dir else None,
            "yolo_summary_json": str(yolo_summary_json) if yolo_summary_json else None,
        },
        "methods": methods,
        "ranking_by_masked_miou": ranking,
        "stratified_by_gap_bin": {
            m: {b: _aggregate(rows) for b, rows in bins.items()}
            for m, bins in by_gap.items()
        },
        "stratified_by_month": {
            m: {mo: _aggregate(rows) for mo, rows in bins.items()}
            for m, bins in by_month.items()
        },
        "gates": gates,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Vizard Arctic Benchmark",
        "",
        f"- Generated (UTC): `{out['generated_at_utc']}`",
        f"- Evaluated scenes: `{len(eval_ids)}`",
        "",
        "## Ranking (masked mIoU)",
    ]
    for i, r in enumerate(ranking, start=1):
        md.append(f"- {i}. `{r['method']}`: `{r['masked_miou']:.4f}`")
    md.extend(
        [
            "",
            "## Gates",
            f"- model_vs_persistence_miou_delta: `{gates['model_vs_persistence_miou_delta']}`",
            f"- model_vs_yolo_status: `{gates['model_vs_yolo_status']}`",
            f"- model_vs_yolo_miou_delta: `{gates['model_vs_yolo_miou_delta']}`",
        ]
    )
    output_md.write_text("\n".join(md), encoding="utf-8")

    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ice-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass"))
    parser.add_argument("--comp-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite"))
    parser.add_argument("--palette", type=Path, default=ROOT / "configs" / "ice_palette.json")
    parser.add_argument("--history-steps", type=int, default=2)
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "backend" / "checkpoints" / "mvp_unet.pt")
    parser.add_argument("--yolo-pred-dir", type=Path, default=None)
    parser.add_argument("--yolo-summary-json", type=Path, default=None)
    parser.add_argument("--max-scenes", type=int, default=180)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--crop-size", type=int, default=512)
    parser.add_argument("--output-json", type=Path, default=ROOT / "storage" / "reports" / "benchmark.json")
    parser.add_argument("--output-md", type=Path, default=ROOT / "storage" / "reports" / "benchmark.md")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = run_benchmark(
        ice_dir=args.ice_dir,
        comp_dir=args.comp_dir,
        palette_path=args.palette,
        history_steps=args.history_steps,
        checkpoint=args.checkpoint if args.checkpoint and args.checkpoint.exists() else None,
        yolo_pred_dir=args.yolo_pred_dir if args.yolo_pred_dir and args.yolo_pred_dir.exists() else None,
        max_scenes=args.max_scenes,
        seed=args.seed,
        crop_size=args.crop_size,
        output_json=args.output_json,
        output_md=args.output_md,
        yolo_summary_json=args.yolo_summary_json if args.yolo_summary_json and args.yolo_summary_json.exists() else None,
    )
    top = out["ranking_by_masked_miou"][0] if out["ranking_by_masked_miou"] else None
    if top:
        print(f"winner={top['method']} masked_miou={top['masked_miou']:.4f}")
    print(f"saved_json={args.output_json}")
    print(f"saved_md={args.output_md}")


if __name__ == "__main__":
    main()
