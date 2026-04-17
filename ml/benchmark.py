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

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.palette import IceClassPalette, load_palette
from app.scene_index import SceneIndex
from ml.metrics import evaluate_segmentation
from ml.predictor import TemporalUNetPredictor


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
        self.predictor = TemporalUNetPredictor(
            checkpoint=checkpoint,
            palette=palette,
            history_steps=history_steps,
            tile_size=crop_size,
            tile_overlap=max(16, crop_size // 8),
            device="auto",
        )

    def predict(
        self,
        *,
        month: int,
        observed: np.ndarray,
        gap: np.ndarray,
        history_cls: list[np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray]:
        return self.predictor.predict(month=month, observed=observed, gap=gap, history_cls=history_cls)


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


def _parse_priority_ids(raw: str) -> list[int]:
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def _load_priority_polygons(path: Path, region_ids: set[int]) -> list[list[tuple[float, float]]]:
    if not path.exists() or not region_ids:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    polys: list[list[tuple[float, float]]] = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        region = int(props.get("region", -1))
        if region not in region_ids:
            continue
        geom = feat.get("geometry", {})
        if geom.get("type") != "Polygon":
            continue
        coords = geom.get("coordinates", [])
        if not coords:
            continue
        ring = coords[0]
        poly = []
        for pt in ring:
            if not isinstance(pt, list) or len(pt) < 2:
                continue
            poly.append((float(pt[0]), float(pt[1])))
        if len(poly) >= 3:
            polys.append(poly)
    return polys


def _priority_mask_from_geo(
    polygons_lonlat: list[list[tuple[float, float]]],
    bounds: list[float],
    shape_hw: tuple[int, int],
) -> np.ndarray:
    h, w = shape_hw
    if not polygons_lonlat:
        return np.zeros((h, w), dtype=np.uint8)

    lon_min, lat_min, lon_max, lat_max = bounds
    dx = max(1e-12, lon_max - lon_min)
    dy = max(1e-12, lat_max - lat_min)

    mask = np.zeros((h, w), dtype=np.uint8)
    for poly in polygons_lonlat:
        pts: list[list[int]] = []
        for lon, lat in poly:
            x = int(round((lon - lon_min) / dx * (w - 1)))
            y = int(round((lat_max - lat) / dy * (h - 1)))
            x = max(0, min(w - 1, x))
            y = max(0, min(h - 1, y))
            pts.append([x, y])
        if len(pts) >= 3:
            cv2.fillPoly(mask, [np.array(pts, dtype=np.int32)], 1)
    return mask


def _sample_synthetic_gap(
    *,
    index: SceneIndex,
    eval_ids: list[str],
    current_sid: str,
    shape_hw: tuple[int, int],
    real_gap: np.ndarray,
    rng: random.Random,
) -> np.ndarray:
    target_h, target_w = shape_hw
    min_pixels = max(256, int(0.005 * target_h * target_w))
    candidates = [sid for sid in eval_ids if sid != current_sid]
    rng.shuffle(candidates)

    for sid in candidates[:12]:
        donor = index.read_gap_mask(sid)
        donor = _resize_nn(donor, shape_hw)
        syn = ((donor == 1) & (real_gap == 0)).astype(np.uint8)
        if int(np.sum(syn)) >= min_pixels:
            return syn

    # deterministic fallback: shifted copy of current real gap, restricted to observed pixels
    shift_y = max(1, target_h // 7)
    shift_x = max(1, target_w // 9)
    shifted = np.roll(real_gap, shift=(shift_y, shift_x), axis=(0, 1))
    syn = ((shifted == 1) & (real_gap == 0)).astype(np.uint8)
    if int(np.sum(syn)) >= min_pixels:
        return syn
    return np.zeros(shape_hw, dtype=np.uint8)


def _per_class_from_cm(cm: np.ndarray, class_ids: np.ndarray) -> tuple[dict[str, float], dict[str, float]]:
    f1: dict[str, float] = {}
    iou: dict[str, float] = {}
    for i, cid in enumerate(class_ids.tolist()):
        tp = float(cm[i, i])
        fp = float(np.sum(cm[:, i]) - tp)
        fn = float(np.sum(cm[i, :]) - tp)
        support = float(np.sum(cm[i, :]))
        key = str(int(cid))
        if support <= 0:
            f1[key] = 0.0
            iou[key] = 0.0
            continue
        prec = tp / max(1.0, tp + fp)
        rec = tp / max(1.0, tp + fn)
        f1[key] = float((2.0 * prec * rec) / max(1e-12, prec + rec))
        iou[key] = float(tp / max(1.0, tp + fp + fn))
    return f1, iou


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
    synthetic_eval: bool = True,
    priority_polygons_path: Path | None = None,
    priority_regions: str = "2,1,7,6,9,10,3",
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

    context_rows: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))
    context_by_gap: dict[str, dict[str, dict[str, list[dict[str, float]]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    context_by_month: dict[str, dict[str, dict[str, list[dict[str, float]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    context_priority: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))
    context_cm: dict[str, dict[str, np.ndarray]] = defaultdict(dict)

    priority_ids = _parse_priority_ids(priority_regions)
    priority_polys = _load_priority_polygons(
        priority_polygons_path if priority_polygons_path else (ROOT / "configs" / "corrected_output_polygons.geojson"),
        set(priority_ids),
    )

    for sid in eval_ids:
        rec = index.get(sid)
        cur_rgb = _read_ice_rgb(rec.iceclass_path)
        gt = palette.rgb_to_class_ids(cur_rgb)
        real_gap = _resize_nn(index.read_gap_mask(sid), gt.shape)
        synthetic_gap = _sample_synthetic_gap(
            index=index,
            eval_ids=eval_ids,
            current_sid=sid,
            shape_hw=gt.shape,
            real_gap=real_gap,
            rng=rng,
        )
        gap_contexts = {"real_gap": real_gap}
        if synthetic_eval and int(np.sum(synthetic_gap)) > 0:
            gap_contexts["synthetic_gap"] = synthetic_gap

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
            hist_gap.append(real_gap)

        geo = index.get_geo_info(sid)
        pr_mask_full = _priority_mask_from_geo(priority_polys, geo.bounds, gt.shape) if priority_polys else None

        yp = _load_yolo_pred(sid, yolo_pred_dir, gt.shape) if yolo_pred_dir is not None else None

        for ctx_name, gap in gap_contexts.items():
            observed = gt.copy()
            observed[gap == 1] = palette.unknown_id

            preds: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            preds["persistence_t1"] = _persistence_t1(observed, gap, hist_cls, hist_gap)
            preds["temporal_fill"] = _temporal_fill(observed, gap, hist_cls, hist_gap)
            if infer is not None:
                preds["temporal_unet"] = infer.predict(
                    month=rec.acquisition_start.month,
                    observed=observed,
                    gap=gap,
                    history_cls=hist_cls,
                )
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
                    class_costs=palette.class_costs,
                )
                row = {
                    "masked_accuracy": m.masked_accuracy,
                    "masked_macro_f1": m.masked_macro_f1,
                    "masked_miou": m.masked_miou,
                    "masked_edge_f1": m.masked_edge_f1,
                    "confidence_brier": m.confidence_brier,
                    "confidence_ece": m.confidence_ece,
                    "recovered_ratio": m.recovered_ratio,
                    "business_cost_mae": m.business_cost_mae,
                }
                context_rows[ctx_name][method].append(row)
                context_by_gap[ctx_name][method][gbin].append(row)
                context_by_month[ctx_name][method][mbin].append(row)

                cm = np.array(m.confusion_matrix, dtype=np.int64)
                if method not in context_cm[ctx_name]:
                    context_cm[ctx_name][method] = np.zeros_like(cm)
                context_cm[ctx_name][method] += cm

                if pr_mask_full is not None:
                    pr_gap = ((pr_mask_full == 1) & (gap == 1)).astype(np.uint8)
                    if int(np.sum(pr_gap)) > 0:
                        mp = evaluate_segmentation(
                            y_true=gt,
                            y_pred=pred,
                            gap_mask=pr_gap,
                            class_ids=palette.class_ids,
                            confidence=conf,
                            class_costs=palette.class_costs,
                        )
                        context_priority[ctx_name][method].append(
                            {
                                "masked_accuracy": mp.masked_accuracy,
                                "masked_macro_f1": mp.masked_macro_f1,
                                "masked_miou": mp.masked_miou,
                                "business_cost_mae": mp.business_cost_mae,
                            }
                        )

    contexts: dict[str, dict] = {}
    for ctx_name, methods_rows in context_rows.items():
        methods_ctx = {}
        for method, rows in methods_rows.items():
            cm = context_cm.get(ctx_name, {}).get(method, np.zeros((len(palette.class_ids), len(palette.class_ids)), dtype=np.int64))
            per_f1, per_iou = _per_class_from_cm(cm, palette.class_ids)
            methods_ctx[method] = {
                "count": len(rows),
                "avg": _aggregate(rows),
                "per_class_f1": per_f1,
                "per_class_iou": per_iou,
                "confusion_matrix": cm.tolist(),
            }

        ranking_ctx = sorted(
            [{"method": k, "masked_miou": v["avg"].get("masked_miou", 0.0)} for k, v in methods_ctx.items()],
            key=lambda x: x["masked_miou"],
            reverse=True,
        )
        contexts[ctx_name] = {
            "methods": methods_ctx,
            "ranking_by_masked_miou": ranking_ctx,
            "stratified_by_gap_bin": {m: {b: _aggregate(rows) for b, rows in bins.items()} for m, bins in context_by_gap[ctx_name].items()},
            "stratified_by_month": {m: {mo: _aggregate(rows) for mo, rows in bins.items()} for m, bins in context_by_month[ctx_name].items()},
            "priority_regions_avg": {m: _aggregate(rows) for m, rows in context_priority[ctx_name].items()},
        }

    primary_context = "synthetic_gap" if ("synthetic_gap" in contexts) else "real_gap"
    methods = contexts.get(primary_context, {}).get("methods", {})
    ranking = contexts.get(primary_context, {}).get("ranking_by_masked_miou", [])

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
            "synthetic_eval": bool(synthetic_eval),
            "priority_polygons_path": str(priority_polygons_path) if priority_polygons_path else None,
            "priority_regions": priority_ids,
            "primary_context": primary_context,
        },
        "primary_context": primary_context,
        "methods": methods,
        "ranking_by_masked_miou": ranking,
        "stratified_by_gap_bin": contexts.get(primary_context, {}).get("stratified_by_gap_bin", {}),
        "stratified_by_month": contexts.get(primary_context, {}).get("stratified_by_month", {}),
        "priority_regions_avg": contexts.get(primary_context, {}).get("priority_regions_avg", {}),
        "contexts": contexts,
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
        f"- Primary context: `{primary_context}`",
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
            "",
            "## Priority Regions",
            f"- Regions used: `{priority_ids}`",
        ]
    )
    for method, vals in contexts.get(primary_context, {}).get("priority_regions_avg", {}).items():
        md.append(f"- `{method}` priority masked_miou: `{vals.get('masked_miou', 0.0):.4f}`")
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
    parser.add_argument("--synthetic-eval", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--priority-polygons", type=Path, default=ROOT / "configs" / "corrected_output_polygons.geojson")
    parser.add_argument("--priority-regions", type=str, default="2,1,7,6,9,10,3")
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
        synthetic_eval=bool(args.synthetic_eval),
        priority_polygons_path=args.priority_polygons if args.priority_polygons and args.priority_polygons.exists() else None,
        priority_regions=args.priority_regions,
    )
    top = out["ranking_by_masked_miou"][0] if out["ranking_by_masked_miou"] else None
    if top:
        print(f"winner={top['method']} masked_miou={top['masked_miou']:.4f}")
    print(f"saved_json={args.output_json}")
    print(f"saved_md={args.output_md}")


if __name__ == "__main__":
    main()
