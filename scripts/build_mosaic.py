"""Build a full-NSR mosaic directly from source GeoTIFF files.

Usage:
    cd C:\\Users\\maksi\\projects\\vizard-arctic
    .\\.venv\\Scripts\\python.exe scripts\\build_mosaic.py

This version reads the raw Composite GeoTIFFs (gap mask from zero pixels)
and IceClass GeoTIFFs directly, producing a full-coverage mosaic without
requiring prior reconstruction. The observed layer shows raw satellite
data, the reconstructed layer fills gaps using temporal history (fast mode).

The output PNG is properly reprojected to Web Mercator (EPSG:3857)
pixel space so it aligns correctly on Leaflet / MapLibre maps.
"""

from __future__ import annotations

import json
import math
import sys
import uuid
from pathlib import Path

import cv2
import numpy as np
import tifffile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.app.db import MetadataDB
from backend.app.palette import IceClassPalette, load_palette
from backend.app.scene_index import SceneIndex, normalize_scene_id
from backend.app.utils import utcnow

STORAGE_DIR = ROOT / "storage"
LAYERS_DIR = STORAGE_DIR / "layers"
DB_PATH = STORAGE_DIR / "metadata.db"
PALETTE_PATH = ROOT / "configs" / "ice_palette.json"
RUSSIA_SHP = ROOT / "configs" / "russia.shp"
SMP_GEOJSON = ROOT / "configs" / "corrected_output_polygons.geojson"

MOSAIC_LON_MIN = 30.0
MOSAIC_LON_MAX = 110.0
MOSAIC_LAT_MIN = 66.0
MOSAIC_LAT_MAX = 83.0

LON_CUTOFF = 130.0

VIEW_NAMES = ["observed", "reconstructed", "confidence", "difference"]

MERC_W = 4000
MERC_H = 1200

SAMPLE_STEP = 4

LAND_COST = 9999.0


def _build_land_mask(mosaic_h: int, mosaic_w: int, x_off: float, y_off: float, scale: float) -> np.ndarray:
    try:
        import shapefile
        sf = shapefile.Reader(str(RUSSIA_SHP))
        mask = np.zeros((mosaic_h, mosaic_w), dtype=np.uint8)
        for shape_rec in sf.shapeRecords():
            parts = list(shape_rec.shape.parts) + [len(shape_rec.shape.points)]
            for i in range(len(parts) - 1):
                pts = shape_rec.shape.points[parts[i]:parts[i + 1]]
                if len(pts) < 3:
                    continue
                pixel_pts = []
                for lon, lat in pts:
                    px, py = _lonlat_to_pixel(lon, lat, x_off, y_off, scale)
                    pixel_pts.append([px, py])
                contour = np.array(pixel_pts, dtype=np.int32).reshape(-1, 1, 2)
                cv2.fillPoly(mask, [contour], 1)
        print(f"  Land mask: {int(np.sum(mask))} pixels ({np.sum(mask)/mask.size*100:.1f}%)")
        return mask
    except Exception as e:
        print(f"  Warning: cannot build land mask: {e}")
        return np.zeros((mosaic_h, mosaic_w), dtype=np.uint8)


def _merc_x(lon: float) -> float:
    return (lon + 180.0) / 360.0


def _merc_y(lat: float) -> float:
    lat_r = math.radians(max(-85.0, min(85.0, lat)))
    return (1.0 - (math.log(math.tan(math.pi / 4.0 + lat_r / 2.0)) / math.pi)) / 2.0


def _inv_merc_x(mx: float) -> float:
    return mx * 360.0 - 180.0


def _inv_merc_y(my: float) -> float:
    y = max(0.0, min(1.0, my))
    lat_r = 2.0 * math.atan(math.exp(math.pi * (1.0 - 2.0 * y))) - math.pi / 2.0
    return math.degrees(lat_r)


def _lonlat_to_pixel(lon: float, lat: float, x_off: float, y_off: float, scale: float) -> tuple[int, int]:
    mx = _merc_x(lon)
    my = _merc_y(lat)
    x = int(round((mx - x_off) * scale))
    y = int(round((my - y_off) * scale))
    return x, y


def _get_geo_info(tif_path: Path) -> dict | None:
    try:
        with tifffile.TiffFile(tif_path) as tf:
            series = tf.series[0]
            h, w = int(series.shape[0]), int(series.shape[1])
            tags = tf.pages[0].tags
            scale = tags[33550].value if 33550 in tags else (1.0, 1.0, 0.0)
            tie = tags[33922].value if 33922 in tags else (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        pixel_w = float(scale[0])
        pixel_h = float(scale[1])
        lon_min = float(tie[3])
        lat_max = float(tie[4])
        lon_max = lon_min + pixel_w * w
        lat_min = lat_max - pixel_h * h
        return {"bounds": [lon_min, lat_min, lon_max, lat_max], "shape": (h, w)}
    except Exception as e:
        print(f"  Warning: cannot read geo info from {tif_path.name}: {e}")
        return None


def _read_iceclass_rgb(rec, palette: IceClassPalette, step: int = 1) -> np.ndarray | None:
    try:
        data = tifffile.imread(rec.iceclass_path)
        if data.ndim == 3 and data.shape[2] >= 3:
            rgb = data[:, :, :3]
            if step > 1:
                rgb = rgb[::step, ::step, :]
            alpha = np.full(rgb.shape[:2], 255, dtype=np.uint8)
            return np.dstack([rgb, alpha])
        if data.ndim == 2:
            if step > 1:
                data = data[::step, ::step]
            rgb = palette.class_ids_to_rgb(data.astype(np.uint8))
            alpha = np.full(data.shape, 255, dtype=np.uint8)
            return np.dstack([rgb, alpha])
        return None
    except Exception as e:
        print(f"  Warning: cannot read iceclass {rec.scene_id[:30]}: {e}")
        return None


def _read_gap_mask(rec, step: int = 1) -> np.ndarray | None:
    try:
        comp = tifffile.imread(rec.composite_path)
        if comp.ndim != 3:
            return None
        if step > 1:
            comp = comp[::step, ::step, :]
        gap = np.all(comp == 0, axis=-1).astype(np.uint8)
        return gap
    except Exception as e:
        print(f"  Warning: cannot read composite {rec.scene_id[:30]}: {e}")
        return None


def _fill_from_history_fast(observed_classes: np.ndarray, gap_mask: np.ndarray, history_maps: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    filled = observed_classes.copy()
    confidence = np.where(gap_mask == 0, 0.95, 0.0).astype(np.float32)

    for i, h_cls in enumerate(history_maps):
        if h_cls.shape != observed_classes.shape:
            h_resized = cv2.resize(h_cls, (observed_classes.shape[1], observed_classes.shape[0]), interpolation=cv2.INTER_NEAREST)
        else:
            h_resized = h_cls
        fill_mask = (gap_mask == 1) & (filled == 0) & (h_resized > 0)
        filled[fill_mask] = h_resized[fill_mask]
        conf_val = max(0.55, 0.9 - i * 0.12)
        confidence[fill_mask] = conf_val

    still_gap = (gap_mask == 1) & (filled == 0)
    if np.any(still_gap):
        from scipy import stats as _stats
        valid = observed_classes[observed_classes > 0]
        if valid.size > 0:
            mode_val = int(np.bincount(valid.flatten()).argmax())
        else:
            mode_val = 1
        filled[still_gap] = mode_val
        confidence[still_gap] = 0.55

    return filled, confidence


def _reproject_and_stamp(
    mosaic: np.ndarray,
    img: np.ndarray,
    bounds: list[float],
    x_off: float,
    y_off: float,
    scale: float,
) -> None:
    lon_min, lat_min, lon_max, lat_max = bounds
    mh, mw = mosaic.shape[:2]
    sh, sw = img.shape[:2]

    x0, y0 = _lonlat_to_pixel(lon_min, lat_max, x_off, y_off, scale)
    x1, y1 = _lonlat_to_pixel(lon_max, lat_min, x_off, y_off, scale)

    x0 = max(0, min(mw, x0))
    y0 = max(0, min(mh, y0))
    x1 = max(0, min(mw, x1))
    y1 = max(0, min(mh, y1))

    if x1 <= x0 or y1 <= y0:
        return

    target_w = x1 - x0
    target_h = y1 - y0
    if target_w < 2 or target_h < 2:
        return

    ox = np.arange(target_w, dtype=np.float32)
    oy = np.arange(target_h, dtype=np.float32)
    ox_grid, oy_grid = np.meshgrid(ox, oy)

    abs_x = (ox_grid + x0) / scale + x_off
    abs_y = (oy_grid + y0) / scale + y_off

    lons = _inv_merc_x(abs_x)
    lats = np.vectorize(_inv_merc_y)(abs_y)

    src_x = (lons - lon_min) / (lon_max - lon_min) * (sw - 1)
    src_y = (lat_max - lats) / (lat_max - lat_min) * (sh - 1)

    valid = (src_x >= 0) & (src_x < sw) & (src_y >= 0) & (src_y < sh)
    src_x = np.where(valid, src_x, 0.0)
    src_y = np.where(valid, src_y, 0.0)

    n_ch = img.shape[2] if img.ndim == 3 else 1
    border_val = tuple([0] * n_ch)
    reprojected = cv2.remap(
        img,
        src_x.astype(np.float32),
        src_y.astype(np.float32),
        cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_val,
    )

    if img.ndim == 3 and img.shape[2] == 4:
        alpha = reprojected[:, :, 3:4].astype(np.float32) / 255.0
        alpha *= valid.astype(np.float32)[:, :, np.newaxis]
        rgb = reprojected[:, :, :3]
        region = mosaic[y0:y1, x0:x1]
        if region.shape[:2] == reprojected.shape[:2]:
            blended = (rgb.astype(np.float32) * alpha + region[:, :, :3].astype(np.float32) * (1.0 - alpha)).astype(np.uint8)
            mosaic[y0:y1, x0:x1, :3] = blended
            mosaic[y0:y1, x0:x1, 3] = np.maximum(
                mosaic[y0:y1, x0:x1, 3],
                (reprojected[:, :, 3] * valid.astype(np.uint8)),
            )
    else:
        ch = min(mosaic.shape[2], reprojected.shape[2] if reprojected.ndim == 3 else 1)
        valid_3ch = np.stack([valid] * ch, axis=-1)
        region = mosaic[y0:y1, x0:x1, :ch]
        src_ch = reprojected[:, :, :ch] if reprojected.ndim == 3 else reprojected
        if region.shape == src_ch.shape:
            mosaic[y0:y1, x0:x1, :ch] = np.where(valid_3ch, src_ch, region)


def _build_route_grid(
    reconstructed_classes: np.ndarray,
    confidence: np.ndarray,
    bounds: list[float],
    grid_size: int = 300,
) -> tuple[np.ndarray, np.ndarray]:
    h, w = reconstructed_classes.shape
    if max(h, w) > grid_size:
        scale = grid_size / float(max(h, w))
        out_h = max(64, int(round(h * scale)))
        out_w = max(64, int(round(w * scale)))
    else:
        out_h, out_w = h, w
    yy = np.linspace(0, h - 1, out_h).astype(np.int32)
    xx = np.linspace(0, w - 1, out_w).astype(np.int32)
    return reconstructed_classes[np.ix_(yy, xx)].astype(np.uint8), confidence[np.ix_(yy, xx)].astype(np.float32)


def _pixel_area_km2(bounds: list[float], shape_hw: tuple[int, int]) -> float:
    from backend.app.route_solver import haversine_km
    lon_min, lat_min, lon_max, lat_max = bounds
    h, w = shape_hw
    mean_lat = (lat_min + lat_max) / 2.0
    mean_lon = (lon_min + lon_max) / 2.0
    dx = haversine_km(lon_min, mean_lat, lon_max, mean_lat) / max(1, w)
    dy = haversine_km(mean_lon, lat_min, mean_lon, lat_max) / max(1, h)
    return dx * dy


def main() -> None:
    print("=== Building NSR Mosaic from raw GeoTIFF (Web Mercator) ===")
    print(f"Storage: {STORAGE_DIR}")

    from backend.app.settings import get_settings
    settings = get_settings()
    scene_index = SceneIndex(settings.dataset_iceclass_dir, settings.dataset_composite_dir)
    print(f"Total scenes in index: {scene_index.total}")

    palette = load_palette(PALETTE_PATH)

    records = scene_index.list_records()
    valid_records = []
    for rec in records:
        geo = scene_index.get_geo_info(rec.scene_id)
        if geo is None:
            continue
        b = geo.bounds
        if b[2] > LON_CUTOFF:
            continue
        if b[3] < MOSAIC_LAT_MIN or b[1] > MOSAIC_LAT_MAX:
            continue
        if b[2] < MOSAIC_LON_MIN:
            continue
        valid_records.append((rec, geo))

    print(f"NSR records: {len(valid_records)}")

    if not valid_records:
        print("ERROR: No NSR records found.")
        sys.exit(1)

    x_off = _merc_x(MOSAIC_LON_MIN)
    y_off = _merc_y(MOSAIC_LAT_MAX)
    x_end = _merc_x(MOSAIC_LON_MAX)
    y_end = _merc_y(MOSAIC_LAT_MIN)

    scale_x = MERC_W / (x_end - x_off)
    scale_y = MERC_H / (y_end - y_off)
    scale = min(scale_x, scale_y)

    mosaic_w = int(round((x_end - x_off) * scale))
    mosaic_h = int(round((y_end - y_off) * scale))

    print(f"Mosaic size: {mosaic_w}x{mosaic_h} px (Web Mercator)")
    print(f"BBox: lon [{MOSAIC_LON_MIN}, {MOSAIC_LON_MAX}] lat [{MOSAIC_LAT_MIN}, {MOSAIC_LAT_MAX}]")

    mosaic_bounds = [MOSAIC_LON_MIN, MOSAIC_LAT_MIN, MOSAIC_LON_MAX, MOSAIC_LAT_MAX]
    mosaic_coordinates = [
        [MOSAIC_LON_MIN, MOSAIC_LAT_MAX],
        [MOSAIC_LON_MAX, MOSAIC_LAT_MAX],
        [MOSAIC_LON_MAX, MOSAIC_LAT_MIN],
        [MOSAIC_LON_MIN, MOSAIC_LAT_MIN],
    ]

    # Sort by date so newest overwrites oldest
    valid_records.sort(key=lambda r: r[0].acquisition_start)

    # Build date groups for temporal gap filling
    from collections import defaultdict
    date_groups: dict[str, list[tuple]] = defaultdict(list)
    for rec, geo in valid_records:
        date_str = rec.acquisition_start.strftime("%Y-%m-%d")
        date_groups[date_str].append((rec, geo))

    dates = sorted(date_groups.keys())
    print(f"Unique dates: {len(dates)}, from {dates[0]} to {dates[-1]}")

    # Pick latest date as primary, build mosaic from that
    # Use ALL scenes for full coverage
    target_date = dates[-1]
    latest_scenes = date_groups[target_date]
    print(f"Latest date: {target_date} ({len(latest_scenes)} scenes)")

    # Collect all scenes from last few dates for history
    history_dates = dates[-5:]  # last 5 dates
    all_scenes_for_date = {}
    for d in history_dates:
        all_scenes_for_date[d] = date_groups[d]

    # Process scenes by date, newest last
    obs_mosaic = np.zeros((mosaic_h, mosaic_w, 4), dtype=np.uint8)
    recon_mosaic = np.zeros((mosaic_h, mosaic_w, 4), dtype=np.uint8)
    conf_mosaic = np.zeros((mosaic_h, mosaic_w, 4), dtype=np.uint8)
    diff_mosaic = np.zeros((mosaic_h, mosaic_w, 4), dtype=np.uint8)

    # Build land mask from Russia.shp
    print("\n--- Building land mask ---")
    land_mask = _build_land_mask(mosaic_h, mosaic_w, x_off, y_off, scale)

    # Step 1: Build observed mosaic from ALL scenes (newest overwrites)
    print("\n--- Building observed layer ---")
    processed = 0
    for rec, geo in valid_records:
        b = geo.bounds
        if b[2] > LON_CUTOFF or b[3] < MOSAIC_LAT_MIN or b[1] > MOSAIC_LAT_MAX or b[2] < MOSAIC_LON_MIN:
            continue

        ice_rgb = _read_iceclass_rgb(rec, palette, step=SAMPLE_STEP)
        if ice_rgb is None:
            continue

        gap = _read_gap_mask(rec, step=SAMPLE_STEP)
        if gap is not None:
            if gap.shape != ice_rgb.shape[:2]:
                gap = cv2.resize(gap, (ice_rgb.shape[1], ice_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
            ice_rgb[gap == 1, 3] = 0

        scaled_bounds = list(b)
        if SAMPLE_STEP > 1:
            scaled_bounds[2] = b[0] + (b[2] - b[0]) * (geo.shape_hw[1] // SAMPLE_STEP) / geo.shape_hw[1]
            scaled_bounds[3] = b[1] + (b[3] - b[1]) * (geo.shape_hw[0] // SAMPLE_STEP) / geo.shape_hw[0]

        _reproject_and_stamp(obs_mosaic, ice_rgb, b, x_off, y_off, scale)
        processed += 1
        if processed % 50 == 0:
            print(f"  Processed {processed} scenes...")

    print(f"Observed: {processed} scenes composited")

    # Step 2: Build gap mask BEFORE filling gaps with ocean color
    print("\n--- Building reconstructed layer ---")
    gap_mask_global = (obs_mosaic[:, :, 3] < 10).astype(np.uint8)
    gap_pixels = int(np.sum(gap_mask_global))
    total_pixels = int(gap_mask_global.size)
    print(f"Gap pixels: {gap_pixels}/{total_pixels} ({gap_pixels/max(1,total_pixels)*100:.1f}%)")

    # NOW fill gaps in observed with dark ocean blue (opaque)
    gap_in_obs = obs_mosaic[:, :, 3] < 10
    obs_mosaic[gap_in_obs] = [8, 15, 40, 255]  # dark ocean blue, fully opaque

    # Mark land as opaque dark grey on observed
    land_color = np.array([60, 60, 60, 255], dtype=np.uint8)
    obs_mosaic[land_mask == 1] = land_color

    # Start reconstruction from observed (with gaps still transparent)
    recon_mosaic[:] = obs_mosaic

    # For gap areas, fill with historical data (older scenes)
    for rec, geo in reversed(valid_records):
        b = geo.bounds
        if b[2] > LON_CUTOFF or b[3] < MOSAIC_LAT_MIN or b[1] > MOSAIC_LAT_MAX or b[2] < MOSAIC_LON_MIN:
            continue

        ice_rgb = _read_iceclass_rgb(rec, palette, step=SAMPLE_STEP)
        if ice_rgb is None:
            continue

        # Only stamp where gap exists
        lon_min, lat_min, lon_max, lat_max = b
        x0, y0 = _lonlat_to_pixel(lon_min, lat_max, x_off, y_off, scale)
        x1, y1 = _lonlat_to_pixel(lon_max, lat_min, x_off, y_off, scale)
        x0, y0 = max(0, min(mosaic_w, x0)), max(0, min(mosaic_h, y0))
        x1, y1 = max(0, min(mosaic_w, x1)), max(0, min(mosaic_h, y1))

        if x1 <= x0 or y1 <= y0:
            continue

        target_w, target_h = x1 - x0, y1 - y0
        if target_w < 2 or target_h < 2:
            continue

        # Reproject history scene
        resized = cv2.resize(ice_rgb, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
        region_gap = gap_mask_global[y0:y1, x0:x1]
        fill_here = (region_gap == 1) & (resized[:, :, 3] > 10)
        if not np.any(fill_here):
            continue

        fill_3ch = np.stack([fill_here] * 3, axis=-1)
        recon_mosaic[y0:y1, x0:x1, :3] = np.where(fill_3ch, resized[:, :, :3], recon_mosaic[y0:y1, x0:x1, :3])
        recon_mosaic[y0:y1, x0:x1, 3] = np.where(fill_here, 255, recon_mosaic[y0:y1, x0:x1, 3])
        # Update gap mask
        gap_mask_global[y0:y1, x0:x1] = np.where(fill_here, 0, gap_mask_global[y0:y1, x0:x1])

    remaining_gaps = int(np.sum(gap_mask_global))
    print(f"Remaining gaps after temporal fill: {remaining_gaps} ({remaining_gaps/max(1,total_pixels)*100:.1f}%)")

    # Fill remaining gaps with mode class
    obs_classes = palette.rgb_to_class_ids(obs_mosaic[:, :, :3])
    valid_classes = obs_classes[obs_classes > 0]
    if valid_classes.size > 0:
        mode_class = int(np.bincount(valid_classes.flatten()).argmax())
    else:
        mode_class = 1
    mode_rgb = palette.class_ids_to_rgb(np.array([[mode_class]]))[0, 0]
    mode_bgra = np.array([*mode_rgb, 255], dtype=np.uint8)

    still_gap = gap_mask_global == 1
    if np.any(still_gap):
        recon_mosaic[still_gap, :3] = mode_rgb
        recon_mosaic[still_gap, 3] = 255

    # Mark land on reconstructed (same dark grey)
    recon_mosaic[land_mask == 1] = land_color

    # Step 3: Confidence map
    print("\n--- Building confidence map ---")
    conf_float = np.full((mosaic_h, mosaic_w), 0.5, dtype=np.float32)
    has_obs = obs_mosaic[:, :, 3] > 10
    conf_float[has_obs] = 0.95
    # Gap areas filled by history get 0.7
    # Areas still gap after history get 0.5
    conf_mosaic[:, :, 0] = ((1.0 - conf_float) * 255 * 2).clip(0, 255).astype(np.uint8)  # R = low conf
    conf_mosaic[:, :, 1] = (conf_float * 255 * 2).clip(0, 255).astype(np.uint8)            # G = high conf
    conf_mosaic[:, :, 2] = 0
    conf_mosaic[:, :, 3] = np.where(has_obs | (recon_mosaic[:, :, 3] > 10), 255, 0)

    # Step 4: Difference map - bright cyan for filled gaps
    print("\n--- Building difference map ---")
    diff_pixels = (obs_mosaic[:, :, 3] < 10) & (recon_mosaic[:, :, 3] > 10)
    # Use original obs gap mask (before we filled gaps with ocean blue)
    original_gap = gap_mask_global == 1
    diff_mosaic[:, :, 0] = 0
    diff_mosaic[:, :, 1] = np.where(original_gap & (recon_mosaic[:, :, 3] > 10), 255, 0).astype(np.uint8)
    diff_mosaic[:, :, 2] = np.where(original_gap & (recon_mosaic[:, :, 3] > 10), 255, 0).astype(np.uint8)
    diff_mosaic[:, :, 3] = np.where(original_gap & (recon_mosaic[:, :, 3] > 10), 255, 0).astype(np.uint8)

    # Save outputs
    print("\n--- Saving ---")
    layer_id = str(uuid.uuid4())
    layer_dir = LAYERS_DIR / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)

    for name, data in [("observed", obs_mosaic), ("reconstructed", recon_mosaic), ("confidence", conf_mosaic), ("difference", diff_mosaic)]:
        out = cv2.cvtColor(data.astype(np.uint8), cv2.COLOR_RGBA2BGRA)
        cv2.imwrite(str(layer_dir / f"{name}.png"), out)
        print(f"  Wrote {name}.png  shape={data.shape}")

    # Route grid
    recon_classes = palette.rgb_to_class_ids(recon_mosaic[:, :, :3])
    route_classes, route_conf = _build_route_grid(recon_classes, conf_float, mosaic_bounds, grid_size=300)

    # Block land in route grid (cost = LAND_COST -> route solver blocks it)
    land_route_mask = cv2.resize(land_mask, (route_classes.shape[1], route_classes.shape[0]), interpolation=cv2.INTER_NEAREST)
    route_classes[land_route_mask == 1] = 0  # no_class -> cost=12 via palette
    route_conf[land_route_mask == 1] = 0.0

    # Save land_cost_grid for route solver
    land_cost_grid = np.where(land_route_mask == 1, LAND_COST, 0.0).astype(np.float32)

    np.savez_compressed(
        layer_dir / "route_grid.npz",
        classes=route_classes,
        confidence=route_conf,
        bounds=np.array(mosaic_bounds, dtype=np.float64),
        land_cost=land_cost_grid,
    )
    print(f"  Wrote route_grid.npz  shape={route_classes.shape}")

    # Summary
    coverage_before = float(1.0 - gap_pixels / max(1, total_pixels))
    coverage_after = 1.0
    pix_area = _pixel_area_km2(mosaic_bounds, recon_classes.shape)
    restored_area_km2 = float(gap_pixels * pix_area)

    gap_conf = conf_float[gap_mask_global == 1] if remaining_gaps < gap_pixels else np.array([0.7])
    mean_conf = float(np.mean(gap_conf)) if gap_conf.size else 0.7

    summary = {
        "layer_id": layer_id,
        "scene_id": "mosaic_nsr",
        "model_mode_requested": "balanced",
        "model_mode_effective": "balanced",
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "restored_area_km2": restored_area_km2,
        "mean_confidence": mean_conf,
        "high_confidence_ratio": float(np.mean(gap_conf >= 0.8)) if gap_conf.size else 0.0,
        "low_confidence_ratio": float(np.mean(gap_conf < 0.6)) if gap_conf.size else 0.0,
        "changed_pixels_ratio": float(np.mean(diff_pixels)) if diff_pixels.size else 0.0,
    }
    (layer_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "layer_id": layer_id,
        "scene_id": "mosaic_nsr",
        "bounds": mosaic_bounds,
        "coordinates": mosaic_coordinates,
        "created_at": utcnow().isoformat(),
        "views": [
            {"name": "observed", "url": f"/api/v1/layers/{layer_id}/observed.png", "opacity": 1.0},
            {"name": "reconstructed", "url": f"/api/v1/layers/{layer_id}/reconstructed.png", "opacity": 0.95},
            {"name": "confidence", "url": f"/api/v1/layers/{layer_id}/confidence.png", "opacity": 0.9},
            {"name": "difference", "url": f"/api/v1/layers/{layer_id}/difference.png", "opacity": 1.0},
        ],
    }
    (layer_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    db = MetadataDB(DB_PATH)
    db.upsert_layer(
        layer_id=layer_id,
        scene_id="mosaic_nsr",
        params_hash="mosaic_full_v4",
        path=str(layer_dir),
        bounds=mosaic_bounds,
        summary=summary,
    )
    print(f"\nRegistered in DB: scene_id=mosaic_nsr, layer_id={layer_id}")
    print(f"Coverage: {coverage_before:.1%} -> {coverage_after:.1%}")
    print(f"Restored: {restored_area_km2:.0f} km2")
    print(f"Mean confidence: {mean_conf:.2f}")
    print(f"\nDone! Mosaic layer: {layer_id}")


if __name__ == "__main__":
    main()
