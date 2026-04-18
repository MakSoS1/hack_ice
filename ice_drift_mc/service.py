from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from numpy.typing import NDArray

from .metrics import compute_metrics, scalar_summary
from .model import DriftModelConfig, RectRegion
from .simulation import simulate_ensemble
from .visualization import create_overview_figure

matplotlib.use("Agg")

Array2D = NDArray[np.float64]
Array3D = NDArray[np.float64]


@dataclass(frozen=True)
class DriftForecastResult:
    trajectories: Array3D
    summary: dict[str, Any]
    figure_path: Path | None
    metrics_path: Path | None
    trajectories_path: Path | None


def find_default_route_grid(repo_root: Path) -> Path:
    candidates = sorted((repo_root / "storage" / "layers").glob("*/route_grid.npz"))
    if not candidates:
        raise FileNotFoundError("No route_grid.npz found under storage/layers")
    return candidates[0]


def extract_domain(bounds: Array2D | NDArray[np.float64]) -> RectRegion:
    lon_min, lat_min, lon_max, lat_max = [float(v) for v in np.asarray(bounds, dtype=np.float64).tolist()]
    return RectRegion(x_min=lon_min, y_min=lat_min, x_max=lon_max, y_max=lat_max)


def infer_forcing_from_grid(confidence: Array2D, bounds: NDArray[np.float64]) -> tuple[Array2D, Array2D]:
    lon_min, lat_min, lon_max, lat_max = [float(v) for v in bounds.tolist()]
    width = max(1e-8, lon_max - lon_min)
    height = max(1e-8, lat_max - lat_min)

    gy, gx = np.gradient(confidence.astype(np.float64))
    flow_grid = np.array([np.mean(gx), -np.mean(gy)], dtype=np.float64)
    scale = np.array([
        width / max(1, confidence.shape[1] - 1),
        height / max(1, confidence.shape[0] - 1),
    ])
    flow = flow_grid * scale

    flow_norm = float(np.linalg.norm(flow))
    target_speed = 0.03 * np.hypot(width, height)
    if flow_norm < 1e-10:
        current = np.array([0.75 * target_speed, 0.35 * target_speed], dtype=np.float64)
    else:
        current = flow / flow_norm * target_speed

    conf_std = float(np.std(confidence))
    rot = np.array([-current[1], current[0]], dtype=np.float64)
    wind = 0.55 * rot + np.array([0.02 * width, -0.02 * height], dtype=np.float64) * (0.8 + conf_std)

    return wind.astype(np.float64), current.astype(np.float64)


def build_time_series(base_vec: Array2D, *, n_steps: int, dt: float, period: float, amp: float) -> Array2D:
    t = np.arange(n_steps, dtype=np.float64) * dt
    mod = 1.0 + amp * np.sin(2.0 * np.pi * t / max(1e-8, period))
    return mod.reshape(-1, 1) * np.asarray(base_vec, dtype=np.float64).reshape(1, 2)


def default_target_area(domain: RectRegion) -> RectRegion:
    return RectRegion(
        x_min=domain.x_min + 0.65 * (domain.x_max - domain.x_min),
        y_min=domain.y_min + 0.55 * (domain.y_max - domain.y_min),
        x_max=domain.x_min + 0.88 * (domain.x_max - domain.x_min),
        y_max=domain.y_min + 0.84 * (domain.y_max - domain.y_min),
    )


def run_drift_forecast(
    *,
    route_grid_path: Path,
    n_simulations: int = 2000,
    horizon: float = 24.0,
    dt: float = 1.0,
    mode: str = "inertial",
    seed: int = 42,
    figure_path: Path | None = None,
    metrics_path: Path | None = None,
    trajectories_path: Path | None = None,
) -> DriftForecastResult:
    with np.load(route_grid_path) as data:
        confidence = data["confidence"].astype(np.float64)
        bounds = data["bounds"].astype(np.float64)

    domain = extract_domain(bounds)
    wind_base, current_base = infer_forcing_from_grid(confidence, bounds)

    config = DriftModelConfig(
        horizon=float(horizon),
        dt=float(dt),
        drag=0.08,
        wind_weight=0.35,
        current_weight=0.85,
        noise_cov=np.array([[0.0045, 0.0012], [0.0012, 0.0038]], dtype=np.float64),
        mode=mode,  # validated in DriftModelConfig
        seed=int(seed),
    )

    wind_series = build_time_series(wind_base, n_steps=config.n_steps, dt=config.dt, period=12.0, amp=0.22)
    current_series = build_time_series(current_base, n_steps=config.n_steps, dt=config.dt, period=18.0, amp=0.12)

    center_x = 0.5 * (domain.x_min + domain.x_max)
    center_y = 0.5 * (domain.y_min + domain.y_max)
    initial_state = np.array([center_x, center_y, 0.0, 0.0], dtype=np.float64)

    target_area = default_target_area(domain)

    trajectories = simulate_ensemble(
        initial_state=initial_state,
        config=config,
        wind=wind_series,
        current=current_series,
        n_simulations=int(n_simulations),
    )
    metrics = compute_metrics(trajectories, target_area=target_area, domain=domain)
    summary = scalar_summary(metrics)
    summary.update(
        {
            "route_grid_path": str(route_grid_path),
            "n_simulations": int(n_simulations),
            "horizon": float(horizon),
            "dt": float(dt),
            "mode": str(mode),
        }
    )

    if figure_path is not None:
        figure_path.parent.mkdir(parents=True, exist_ok=True)
        fig = create_overview_figure(
            trajectories,
            mean_trajectory=metrics.mean_trajectory,
            domain=domain,
            target_area=target_area,
            sample_size=min(250, int(n_simulations)),
        )
        fig.savefig(figure_path, dpi=140)

    if metrics_path is not None:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if trajectories_path is not None:
        trajectories_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            trajectories_path,
            trajectories=trajectories.astype(np.float64),
            bounds=bounds.astype(np.float64),
            confidence=confidence.astype(np.float64),
        )

    return DriftForecastResult(
        trajectories=trajectories,
        summary=summary,
        figure_path=figure_path,
        metrics_path=metrics_path,
        trajectories_path=trajectories_path,
    )
