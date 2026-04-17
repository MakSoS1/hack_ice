from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.palette import load_palette
from app.scene_index import SceneIndex, parse_scene_name  # noqa: E402


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "p05": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0, "max": 0.0, "mean": 0.0}
    arr = np.array(values, dtype=np.float64)
    return {
        "min": float(np.min(arr)),
        "p05": float(np.quantile(arr, 0.05)),
        "p25": float(np.quantile(arr, 0.25)),
        "p50": float(np.quantile(arr, 0.50)),
        "p75": float(np.quantile(arr, 0.75)),
        "p95": float(np.quantile(arr, 0.95)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


def _ratio_bins(values: list[float]) -> dict[str, int]:
    bins = {
        "lt_10": 0,
        "10_20": 0,
        "20_30": 0,
        "30_40": 0,
        "40_50": 0,
        "ge_50": 0,
    }
    for v in values:
        p = v * 100.0
        if p < 10:
            bins["lt_10"] += 1
        elif p < 20:
            bins["10_20"] += 1
        elif p < 30:
            bins["20_30"] += 1
        elif p < 40:
            bins["30_40"] += 1
        elif p < 50:
            bins["40_50"] += 1
        else:
            bins["ge_50"] += 1
    return bins


def _safe_read_rgb(path: Path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise RuntimeError(f"Failed to read {path}")
    if bgr.ndim != 3 or bgr.shape[-1] != 3:
        raise ValueError(f"Unexpected RGB shape={bgr.shape} for {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _aux_gap_ratio(comp_path: Path) -> float | None:
    aux = comp_path.with_suffix(comp_path.suffix + ".aux.xml")
    if not aux.exists():
        return None
    try:
        root = ET.fromstring(aux.read_text(encoding="utf-8"))
        for mdi in root.findall(".//MDI"):
            if mdi.attrib.get("key") == "STATISTICS_VALID_PERCENT" and mdi.text:
                valid = float(mdi.text)
                return float(np.clip(1.0 - valid / 100.0, 0.0, 1.0))
    except Exception:  # noqa: BLE001
        return None
    return None


def run_audit(
    *,
    ice_dir: Path,
    comp_dir: Path,
    palette_path: Path,
    output_json: Path,
    output_md: Path,
    class_sample_scenes: int,
    class_stride: int,
    full_gap_pass: bool,
    max_scenes: int,
) -> dict:
    index = SceneIndex(ice_dir, comp_dir)
    palette = load_palette(palette_path)

    ice_files = sorted(ice_dir.glob("*.tif"))
    comp_files = sorted(comp_dir.glob("*.tif"))
    paired_all = index.list_records()
    if max_scenes > 0 and max_scenes < len(paired_all):
        rng = np.random.default_rng(42)
        sample_idx = np.sort(rng.choice(len(paired_all), size=max_scenes, replace=False))
        paired = [paired_all[int(i)] for i in sample_idx]
    else:
        paired = paired_all

    all_scene_ids = [r.scene_id for r in paired]
    invalid_scene_ids: list[str] = []

    mission_counts = Counter()
    mode_counts = Counter()
    product_counts = Counter()
    level_pol_counts = Counter()
    orbit_prefix_counts = Counter()

    for sid in all_scene_ids:
        try:
            p = parse_scene_name(sid)
            mission_counts[p.mission] += 1
            mode_counts[p.acquisition_mode] += 1
            product_counts[p.product_type] += 1
            level_pol_counts[p.level_polarization] += 1
            orbit_prefix_counts[p.absolute_orbit[:3]] += 1
        except Exception:  # noqa: BLE001
            invalid_scene_ids.append(sid)

    starts = [r.acquisition_start for r in paired]
    starts_sorted = sorted(starts)
    deltas_min: list[float] = []
    for a, b in zip(starts_sorted[:-1], starts_sorted[1:], strict=False):
        deltas_min.append((b - a).total_seconds() / 60.0)

    shape_counts = Counter()
    widths: list[int] = []
    heights: list[int] = []
    lon_mins: list[float] = []
    lon_maxs: list[float] = []
    lat_mins: list[float] = []
    lat_maxs: list[float] = []

    gap_ratios: list[float] = []
    gap_by_month: dict[int, list[float]] = defaultdict(list)

    for rec in paired:
        geo = index.get_geo_info(rec.scene_id)
        h, w = geo.shape_hw
        shape_counts[f"{h}x{w}"] += 1
        heights.append(h)
        widths.append(w)

        lon_mins.append(float(geo.bounds[0]))
        lat_mins.append(float(geo.bounds[1]))
        lon_maxs.append(float(geo.bounds[2]))
        lat_maxs.append(float(geo.bounds[3]))

        gr = _aux_gap_ratio(rec.composite_path)
        if gr is None or full_gap_pass:
            gap = index.read_gap_mask(rec.scene_id)
            gr = float(np.mean(gap))
        else:
            gr = float(gr)
        gap_ratios.append(gr)
        gap_by_month[rec.acquisition_start.month].append(gr)

    class_hist = np.zeros(len(palette.class_ids), dtype=np.float64)
    class_scene_ids = all_scene_ids[: min(class_sample_scenes, len(all_scene_ids))]
    for sid in class_scene_ids:
        rec = index.get(sid)
        rgb = _safe_read_rgb(rec.iceclass_path)
        if class_stride > 1:
            rgb = rgb[::class_stride, ::class_stride]
        cls = palette.rgb_to_class_ids(rgb)
        vals, counts = np.unique(cls, return_counts=True)
        for v, c in zip(vals, counts, strict=False):
            try:
                idx = int(np.where(palette.class_ids == v)[0][0])
                class_hist[idx] += int(c)
            except Exception:  # noqa: BLE001
                continue

    class_share: dict[str, float] = {}
    total_cls = float(np.sum(class_hist))
    if total_cls > 0:
        for i, cid in enumerate(palette.class_ids):
            class_share[f"{int(cid)}:{palette.class_names[i]}"] = float(class_hist[i] / total_cls)

    report = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "paths": {
            "ice_dir": str(ice_dir),
            "composite_dir": str(comp_dir),
            "palette_path": str(palette_path),
        },
        "counts": {
            "ice_tif": len(ice_files),
            "composite_tif": len(comp_files),
            "paired_intersection": len(paired_all),
            "paired_evaluated": len(paired),
            "ice_unpaired_estimate": max(0, len(ice_files) - len(paired_all)),
            "composite_unpaired_estimate": max(0, len(comp_files) - len(paired_all)),
        },
        "filename_validation": {
            "invalid_scene_ids": len(invalid_scene_ids),
            "invalid_examples": invalid_scene_ids[:10],
            "mission_counts": dict(mission_counts),
            "mode_counts": dict(mode_counts),
            "product_counts": dict(product_counts),
            "level_polarization_counts": dict(level_pol_counts),
            "orbit_prefix_counts_top10": dict(orbit_prefix_counts.most_common(10)),
        },
        "time_distribution": {
            "first_scene_utc": starts_sorted[0].isoformat() if starts_sorted else None,
            "last_scene_utc": starts_sorted[-1].isoformat() if starts_sorted else None,
            "delta_minutes_summary": _quantiles(deltas_min),
            "delta_minutes_median": float(median(deltas_min)) if deltas_min else 0.0,
        },
        "geometry": {
            "shape_counts_top10": dict(shape_counts.most_common(10)),
            "height_summary": _quantiles([float(x) for x in heights]),
            "width_summary": _quantiles([float(x) for x in widths]),
            "lon_range": [float(min(lon_mins)), float(max(lon_maxs))] if lon_mins and lon_maxs else [0.0, 0.0],
            "lat_range": [float(min(lat_mins)), float(max(lat_maxs))] if lat_mins and lat_maxs else [0.0, 0.0],
        },
        "gap_ratio": {
            "summary": _quantiles(gap_ratios),
            "bins": _ratio_bins(gap_ratios),
            "by_month_mean": {
                str(k): float(np.mean(v)) if v else math.nan
                for k, v in sorted(gap_by_month.items())
            },
        },
        "class_histogram_sample": {
            "sample_scenes": len(class_scene_ids),
            "sample_stride": class_stride,
            "class_share": class_share,
        },
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Vizard Arctic Data Audit",
        "",
        f"- Generated (UTC): `{report['generated_at_utc']}`",
        f"- Ice TIFF files: `{report['counts']['ice_tif']}`",
        f"- Composite TIFF files: `{report['counts']['composite_tif']}`",
        f"- Paired scenes (intersection): `{report['counts']['paired_intersection']}`",
        f"- Paired scenes evaluated in this pass: `{report['counts']['paired_evaluated']}`",
        "",
        "## Filename Validation",
        f"- Invalid normalized scene ids: `{report['filename_validation']['invalid_scene_ids']}`",
        f"- Missions: `{report['filename_validation']['mission_counts']}`",
        f"- Modes: `{report['filename_validation']['mode_counts']}`",
        f"- Product blocks: `{report['filename_validation']['product_counts']}`",
        f"- Level/polarization blocks: `{report['filename_validation']['level_polarization_counts']}`",
        "",
        "## Gap Ratio",
        f"- Mean gap ratio: `{report['gap_ratio']['summary']['mean']:.4f}`",
        f"- Median gap ratio: `{report['gap_ratio']['summary']['p50']:.4f}`",
        f"- P95 gap ratio: `{report['gap_ratio']['summary']['p95']:.4f}`",
        f"- Bins: `{report['gap_ratio']['bins']}`",
        "",
        "## Temporal Density",
        f"- First scene: `{report['time_distribution']['first_scene_utc']}`",
        f"- Last scene: `{report['time_distribution']['last_scene_utc']}`",
        f"- Median inter-scene delta (minutes): `{report['time_distribution']['delta_minutes_median']:.2f}`",
        "",
        "## Geometry",
        f"- Top shapes: `{report['geometry']['shape_counts_top10']}`",
        f"- Longitude range: `{report['geometry']['lon_range']}`",
        f"- Latitude range: `{report['geometry']['lat_range']}`",
    ]
    output_md.write_text("\n".join(md), encoding="utf-8")

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ice-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass"))
    parser.add_argument("--comp-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite"))
    parser.add_argument("--palette", type=Path, default=ROOT / "configs" / "ice_palette.json")
    parser.add_argument("--output-json", type=Path, default=ROOT / "storage" / "reports" / "data_audit.json")
    parser.add_argument("--output-md", type=Path, default=ROOT / "storage" / "reports" / "data_audit.md")
    parser.add_argument("--class-sample-scenes", type=int, default=150)
    parser.add_argument("--class-stride", type=int, default=8)
    parser.add_argument("--full-gap-pass", action="store_true", help="Read every composite raster to compute exact gap ratio")
    parser.add_argument("--max-scenes", type=int, default=0, help="0 means full dataset; otherwise random sampled scene count")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_audit(
        ice_dir=args.ice_dir,
        comp_dir=args.comp_dir,
        palette_path=args.palette,
        output_json=args.output_json,
        output_md=args.output_md,
        class_sample_scenes=args.class_sample_scenes,
        class_stride=args.class_stride,
        full_gap_pass=args.full_gap_pass,
        max_scenes=args.max_scenes,
    )
    print(f"paired={report['counts']['paired_intersection']} invalid_names={report['filename_validation']['invalid_scene_ids']}")
    print(f"gap_mean={report['gap_ratio']['summary']['mean']:.4f} gap_p95={report['gap_ratio']['summary']['p95']:.4f}")
    print(f"saved_json={args.output_json}")
    print(f"saved_md={args.output_md}")


if __name__ == "__main__":
    main()
