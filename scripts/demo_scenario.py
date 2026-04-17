from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.palette import load_palette
from app.db import MetadataDB
from app.reconstruction import run_reconstruction
from app.route_solver import solve_astar
from app.scene_index import SceneIndex
from app.utils import params_hash


def _scene_triplet(index: SceneIndex, start_scene_id: str | None) -> list[str]:
    ids = index.list_scene_ids()
    if len(ids) < 3:
        raise RuntimeError("Need at least 3 scenes for demo scenario")
    if start_scene_id and start_scene_id in ids:
        i = ids.index(start_scene_id)
        if i + 2 < len(ids):
            return [ids[i], ids[i + 1], ids[i + 2]]
    # fallback: latest 3 scenes
    return ids[-3:]


def _safe_route_points(bounds: list[float]) -> tuple[tuple[float, float], tuple[float, float]]:
    lon_min, lat_min, lon_max, lat_max = bounds
    s_lon = lon_min + 0.18 * (lon_max - lon_min)
    s_lat = lat_min + 0.22 * (lat_max - lat_min)
    e_lon = lon_max - 0.18 * (lon_max - lon_min)
    e_lat = lat_max - 0.22 * (lat_max - lat_min)
    return (s_lon, s_lat), (e_lon, e_lat)


def _solve_route_for_layer(layer_dir: Path, palette, vessel_class: str = "Arc7", confidence_penalty: float = 2.0) -> dict:
    npz = np.load(layer_dir / "route_grid.npz")
    classes = npz["classes"].astype(np.uint8)
    conf = npz["confidence"].astype(np.float32)
    bounds = npz["bounds"].astype(np.float64).tolist()
    npz.close()

    cost = palette.class_cost_grid(classes)
    (s_lon, s_lat), (e_lon, e_lat) = _safe_route_points(bounds)
    route = solve_astar(
        cost_grid=cost,
        confidence_grid=conf,
        bounds=bounds,
        start_lon=float(s_lon),
        start_lat=float(s_lat),
        end_lon=float(e_lon),
        end_lat=float(e_lat),
        vessel_class=vessel_class,
        confidence_penalty=confidence_penalty,
    )
    return {
        "distance_km": float(route.distance_km),
        "eta_hours": float(route.distance_km / 23.0),
        "risk_score": float(route.risk_score),
        "confidence_score": float(route.confidence_score),
        "total_cost": float(route.total_cost),
    }


def _build_gif(layer_dirs: list[Path], out_path: Path) -> None:
    frames: list[Image.Image] = []
    for layer_dir in layer_dirs:
        img = Image.open(layer_dir / "reconstructed.png").convert("RGBA")
        frames.append(img)
    if not frames:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=850,
        loop=0,
        disposal=2,
    )


def run_demo(
    *,
    ice_dir: Path,
    comp_dir: Path,
    palette_path: Path,
    storage_dir: Path,
    checkpoint_path: Path,
    start_scene_id: str | None,
    model_mode: str,
) -> dict:
    index = SceneIndex(ice_dir, comp_dir)
    palette = load_palette(palette_path)
    db = MetadataDB(storage_dir / "metadata.db")

    scene_ids = _scene_triplet(index, start_scene_id=start_scene_id)
    layers: list[dict] = []
    layer_dirs: list[Path] = []

    for sid in scene_ids:
        artifacts = run_reconstruction(
            scene_index=index,
            palette=palette,
            storage_dir=storage_dir,
            scene_id=sid,
            history_steps=1,
            model_mode=model_mode,
            preview_max_width=1024,
            route_grid_size=256,
            model_checkpoint_path=checkpoint_path,
            model_device="cuda",
            model_input_size=256,
            model_tile_overlap=64,
        )
        route = _solve_route_for_layer(artifacts.layer_dir, palette=palette)
        phash = params_hash(sid, history_steps=1, model_mode=model_mode, aoi_bbox=None)
        db.upsert_layer(
            layer_id=artifacts.layer_id,
            scene_id=sid,
            params_hash=phash,
            path=str(artifacts.layer_dir),
            bounds=artifacts.bounds,
            summary=artifacts.summary,
        )
        layers.append(
            {
                "scene_id": sid,
                "layer_id": artifacts.layer_id,
                "summary": artifacts.summary,
                "route": route,
                "layer_dir": str(artifacts.layer_dir),
            }
        )
        layer_dirs.append(artifacts.layer_dir)

    gif_path = storage_dir / "reports" / f"demo_ice_motion_{uuid.uuid4().hex[:8]}.gif"
    _build_gif(layer_dirs, gif_path)

    route_delta = None
    if len(layers) >= 2:
        route_delta = {
            "distance_km_delta_last_minus_first": float(layers[-1]["route"]["distance_km"] - layers[0]["route"]["distance_km"]),
            "risk_delta_last_minus_first": float(layers[-1]["route"]["risk_score"] - layers[0]["route"]["risk_score"]),
            "confidence_delta_last_minus_first": float(
                layers[-1]["route"]["confidence_score"] - layers[0]["route"]["confidence_score"]
            ),
        }

    out = {
        "model_mode": model_mode,
        "checkpoint": str(checkpoint_path),
        "scenes": scene_ids,
        "layers": layers,
        "route_delta": route_delta,
        "gif_path": str(gif_path),
    }

    reports = storage_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    payload_json = reports / "demo_scenario.json"
    payload_md = reports / "demo_scenario.md"
    payload_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Demo Scenario",
        "",
        f"- Model mode: `{model_mode}`",
        f"- Checkpoint: `{checkpoint_path}`",
        f"- Scenes: `{', '.join(scene_ids)}`",
        "",
        "## Layer Results",
    ]
    for i, layer in enumerate(layers, start=1):
        s = layer["summary"]
        r = layer["route"]
        md.append(
            f"- {i}. `{layer['scene_id']}` | coverage `{s['coverage_before']:.3f} -> {s['coverage_after']:.3f}` | "
            f"route `{r['distance_km']:.1f} km`, risk `{r['risk_score']:.3f}`, conf `{r['confidence_score']:.3f}`"
        )
    if route_delta is not None:
        md.extend(
            [
                "",
                "## Route Delta (Last - First)",
                f"- distance_km_delta: `{route_delta['distance_km_delta_last_minus_first']:.2f}`",
                f"- risk_delta: `{route_delta['risk_delta_last_minus_first']:.4f}`",
                f"- confidence_delta: `{route_delta['confidence_delta_last_minus_first']:.4f}`",
            ]
        )
    md.extend(["", "## Animation", f"- GIF: `{gif_path}`"])
    payload_md.write_text("\n".join(md), encoding="utf-8")

    return {
        "json": str(payload_json),
        "md": str(payload_md),
        "gif": str(gif_path),
        "scenes": scene_ids,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--ice-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass"))
    p.add_argument("--comp-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite"))
    p.add_argument("--palette", type=Path, default=ROOT / "configs" / "ice_palette.json")
    p.add_argument("--storage", type=Path, default=ROOT / "storage")
    p.add_argument("--checkpoint", type=Path, default=ROOT / "backend" / "checkpoints" / "mvp_unet.pt")
    p.add_argument("--start-scene-id", type=str, default=None)
    p.add_argument("--model-mode", type=str, default="balanced", choices=["fast", "balanced", "precise"])
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out = run_demo(
        ice_dir=args.ice_dir,
        comp_dir=args.comp_dir,
        palette_path=args.palette,
        storage_dir=args.storage,
        checkpoint_path=args.checkpoint,
        start_scene_id=args.start_scene_id,
        model_mode=args.model_mode,
    )
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
