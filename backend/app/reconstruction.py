from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .palette import IceClassPalette
from .route_solver import downsample_grid, haversine_km
from .scene_index import SceneIndex
from .utils import utcnow


@dataclass
class ReconstructionArtifacts:
    layer_id: str
    layer_dir: Path
    scene_id: str
    bounds: list[float]
    coordinates: list[list[float]]
    summary: dict[str, float]


def _read_ice_rgb(path: Path) -> np.ndarray:
    # cv2 reads TIFF reliably with bundled codecs; convert BGR->RGB.
    bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise RuntimeError(f"Failed to read IceClass TIFF: {path}")
    if bgr.ndim != 3 or bgr.shape[-1] != 3:
        raise ValueError(f"Unexpected IceClass shape={bgr.shape} for {path}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb


def _resize_nearest(mask: np.ndarray, shape_hw: tuple[int, int]) -> np.ndarray:
    h, w = shape_hw
    out = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
    return out


def _confidence_to_rgb(conf: np.ndarray) -> np.ndarray:
    # red->yellow->green
    conf = np.clip(conf, 0.0, 1.0)
    r = np.where(conf < 0.5, 255, ((1.0 - conf) * 2.0 * 255.0)).astype(np.uint8)
    g = np.where(conf < 0.5, (conf * 2.0 * 255.0), 255).astype(np.uint8)
    b = np.zeros_like(r, dtype=np.uint8)
    return np.stack([r, g, b], axis=-1)


def _global_mode(class_map: np.ndarray, observed_mask: np.ndarray) -> int:
    vals = class_map[observed_mask]
    if vals.size == 0:
        return int(np.bincount(class_map.reshape(-1)).argmax())
    counts = np.bincount(vals.reshape(-1))
    return int(np.argmax(counts))


def _fill_from_history(
    observed_classes: np.ndarray,
    gap_mask: np.ndarray,
    history_classes: list[np.ndarray],
    history_gap_masks: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    recon = observed_classes.copy()
    conf = np.where(gap_mask == 0, 1.0, 0.0).astype(np.float32)

    for i, (hist_cls, hist_gap) in enumerate(zip(history_classes, history_gap_masks, strict=False)):
        fill_mask = (gap_mask == 1) & (conf == 0.0) & (hist_gap == 0)
        if not np.any(fill_mask):
            continue
        recon[fill_mask] = hist_cls[fill_mask]
        conf[fill_mask] = max(0.6, 0.9 - i * 0.12)

    remaining = (gap_mask == 1) & (conf == 0.0)
    if np.any(remaining):
        mode_cls = _global_mode(observed_classes, gap_mask == 0)
        recon[remaining] = mode_cls
        conf[remaining] = 0.55

    return recon, conf


def _prepare_preview(arr: np.ndarray, max_width: int, interpolation: int) -> np.ndarray:
    h, w = arr.shape[:2]
    if w <= max_width:
        return arr
    scale = max_width / float(w)
    out_w = max_width
    out_h = max(1, int(round(h * scale)))
    return cv2.resize(arr, (out_w, out_h), interpolation=interpolation)


def _rgba(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    return np.concatenate([rgb, alpha[..., None]], axis=-1).astype(np.uint8)


def _write_png(path: Path, rgba: np.ndarray) -> None:
    bgra = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)
    cv2.imwrite(str(path), bgra)


def _pixel_area_km2(bounds: list[float], shape_hw: tuple[int, int]) -> float:
    lon_min, lat_min, lon_max, lat_max = bounds
    h, w = shape_hw
    mean_lat = (lat_min + lat_max) / 2.0
    mean_lon = (lon_min + lon_max) / 2.0
    dx = haversine_km(lon_min, mean_lat, lon_max, mean_lat) / max(1, w)
    dy = haversine_km(mean_lon, lat_min, mean_lon, lat_max) / max(1, h)
    return dx * dy


def run_reconstruction(
    *,
    scene_index: SceneIndex,
    palette: IceClassPalette,
    storage_dir: Path,
    scene_id: str,
    history_steps: int,
    model_mode: str,
    preview_max_width: int,
    route_grid_size: int,
) -> ReconstructionArtifacts:
    _ = model_mode  # placeholder for future model-switch logic

    rec = scene_index.get(scene_id)
    geo = scene_index.get_geo_info(scene_id)

    ice_rgb = _read_ice_rgb(rec.iceclass_path)
    observed_classes = palette.rgb_to_class_ids(ice_rgb)

    gap_mask_comp = scene_index.read_gap_mask(scene_id)
    gap_mask = _resize_nearest(gap_mask_comp, observed_classes.shape)

    history = scene_index.get_history(scene_id, steps=history_steps)
    hist_classes: list[np.ndarray] = []
    hist_gaps: list[np.ndarray] = []
    for hrec in history:
        h_rgb = _read_ice_rgb(hrec.iceclass_path)
        h_cls = palette.rgb_to_class_ids(h_rgb)
        h_gap = _resize_nearest(scene_index.read_gap_mask(hrec.scene_id), h_cls.shape)

        # Resample history to current scene raster dimensions.
        h_cls_resized = _resize_nearest(h_cls, observed_classes.shape)
        h_gap_resized = _resize_nearest(h_gap, observed_classes.shape)
        hist_classes.append(h_cls_resized)
        hist_gaps.append(h_gap_resized)

    reconstructed_classes, confidence = _fill_from_history(
        observed_classes=observed_classes,
        gap_mask=gap_mask,
        history_classes=hist_classes,
        history_gap_masks=hist_gaps,
    )

    difference = np.zeros_like(observed_classes, dtype=np.uint8)
    changed = (gap_mask == 1) & (reconstructed_classes != observed_classes)
    difference[changed] = 1

    observed_rgb = palette.class_ids_to_rgb(observed_classes)
    reconstructed_rgb = palette.class_ids_to_rgb(reconstructed_classes)
    confidence_rgb = _confidence_to_rgb(confidence)

    observed_alpha = np.where(gap_mask == 1, 40, 180).astype(np.uint8)
    reconstructed_alpha = np.where(gap_mask == 1, 215, 120).astype(np.uint8)
    confidence_alpha = np.where(gap_mask == 1, 190, 90).astype(np.uint8)
    diff_alpha = np.where(difference == 1, 230, 0).astype(np.uint8)

    diff_rgb = np.zeros_like(observed_rgb)
    diff_rgb[..., 0] = 255
    diff_rgb[..., 1] = np.where(difference == 1, 0, 0)
    diff_rgb[..., 2] = np.where(difference == 1, 250, 0)

    observed_rgba = _rgba(observed_rgb, observed_alpha)
    reconstructed_rgba = _rgba(reconstructed_rgb, reconstructed_alpha)
    confidence_rgba = _rgba(confidence_rgb, confidence_alpha)
    difference_rgba = _rgba(diff_rgb, diff_alpha)

    observed_prev = _prepare_preview(observed_rgba, max_width=preview_max_width, interpolation=cv2.INTER_NEAREST)
    recon_prev = _prepare_preview(reconstructed_rgba, max_width=preview_max_width, interpolation=cv2.INTER_NEAREST)
    conf_prev = _prepare_preview(confidence_rgba, max_width=preview_max_width, interpolation=cv2.INTER_LINEAR)
    diff_prev = _prepare_preview(difference_rgba, max_width=preview_max_width, interpolation=cv2.INTER_NEAREST)

    layer_id = str(uuid.uuid4())
    layer_dir = storage_dir / "layers" / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)

    _write_png(layer_dir / "observed.png", observed_prev)
    _write_png(layer_dir / "reconstructed.png", recon_prev)
    _write_png(layer_dir / "confidence.png", conf_prev)
    _write_png(layer_dir / "difference.png", diff_prev)

    # Route grids are downsampled for A* speed.
    in_h, in_w = reconstructed_classes.shape
    if max(in_h, in_w) > route_grid_size:
        scale = route_grid_size / float(max(in_h, in_w))
        out_h = max(64, int(round(in_h * scale)))
        out_w = max(64, int(round(in_w * scale)))
    else:
        out_h, out_w = in_h, in_w

    route_classes = downsample_grid(reconstructed_classes, (out_h, out_w), mode="nearest").astype(np.uint8)
    route_conf = downsample_grid(confidence, (out_h, out_w), mode="nearest").astype(np.float32)

    np.savez_compressed(
        layer_dir / "route_grid.npz",
        classes=route_classes,
        confidence=route_conf,
        bounds=np.array(geo.bounds, dtype=np.float64),
    )

    gap_pixels = int(np.sum(gap_mask == 1))
    total_pixels = int(gap_mask.size)
    coverage_before = float(1.0 - gap_pixels / max(1, total_pixels))
    coverage_after = 1.0

    pix_area = _pixel_area_km2(geo.bounds, observed_classes.shape)
    restored_area_km2 = float(gap_pixels * pix_area)

    restored_conf = confidence[gap_mask == 1]
    mean_conf = float(np.mean(restored_conf)) if restored_conf.size else 1.0
    high_conf = float(np.mean(restored_conf >= 0.8)) if restored_conf.size else 1.0
    low_conf = float(np.mean(restored_conf < 0.6)) if restored_conf.size else 0.0
    changed_ratio = float(np.mean(changed[gap_mask == 1])) if restored_conf.size else 0.0

    summary = {
        "layer_id": layer_id,
        "scene_id": scene_id,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "restored_area_km2": restored_area_km2,
        "mean_confidence": mean_conf,
        "high_confidence_ratio": high_conf,
        "low_confidence_ratio": low_conf,
        "changed_pixels_ratio": changed_ratio,
    }

    (layer_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "layer_id": layer_id,
        "scene_id": scene_id,
        "bounds": geo.bounds,
        "coordinates": geo.coordinates,
        "created_at": utcnow().isoformat(),
        "views": [
            {"name": "observed", "url": f"/api/v1/layers/{layer_id}/observed.png", "opacity": 0.9},
            {"name": "reconstructed", "url": f"/api/v1/layers/{layer_id}/reconstructed.png", "opacity": 0.9},
            {"name": "confidence", "url": f"/api/v1/layers/{layer_id}/confidence.png", "opacity": 0.85},
            {"name": "difference", "url": f"/api/v1/layers/{layer_id}/difference.png", "opacity": 0.9},
        ],
    }
    (layer_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return ReconstructionArtifacts(
        layer_id=layer_id,
        layer_dir=layer_dir,
        scene_id=scene_id,
        bounds=geo.bounds,
        coordinates=geo.coordinates,
        summary=summary,
    )
