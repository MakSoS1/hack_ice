from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .model import RectRegion

Array1D = NDArray[np.float64]
Array2D = NDArray[np.float64]
Array3D = NDArray[np.float64]


@dataclass(frozen=True)
class MonteCarloMetrics:
    mean_trajectory: Array2D
    speed_magnitude: Array2D
    mean_speed_magnitude: Array1D
    displacement: Array2D
    mean_displacement: Array1D
    position_covariance: Array3D
    area_probability_over_time: Array1D | None
    area_hit_probability: float | None
    boundary_violation_probability_over_time: Array1D | None
    boundary_exit_probability: float | None


def compute_metrics(
    trajectories: Array3D,
    *,
    target_area: RectRegion | None = None,
    domain: RectRegion | None = None,
) -> MonteCarloMetrics:
    if trajectories.ndim != 3 or trajectories.shape[2] != 4:
        raise ValueError(f"trajectories must have shape (N, S, 4), got {trajectories.shape}")

    n_sim, _, _ = trajectories.shape

    positions = trajectories[:, :, :2]
    velocities = trajectories[:, :, 2:]

    mean_trajectory = np.mean(trajectories, axis=0)

    speed_magnitude = np.linalg.norm(velocities, axis=2)
    mean_speed_magnitude = np.mean(speed_magnitude, axis=0)

    initial_pos = positions[:, :1, :]
    displacement = np.linalg.norm(positions - initial_pos, axis=2)
    mean_displacement = np.mean(displacement, axis=0)

    centered = positions - np.mean(positions, axis=0, keepdims=True)
    if n_sim > 1:
        position_covariance = np.einsum("nsi,nsj->sij", centered, centered) / float(n_sim - 1)
    else:
        position_covariance = np.zeros((positions.shape[1], 2, 2), dtype=np.float64)

    area_probability_over_time: Array1D | None = None
    area_hit_probability: float | None = None
    if target_area is not None:
        inside = target_area.contains(positions.reshape(-1, 2)).reshape(positions.shape[0], positions.shape[1])
        area_probability_over_time = np.mean(inside, axis=0).astype(np.float64)
        area_hit_probability = float(np.mean(np.any(inside, axis=1)))

    boundary_violation_probability_over_time: Array1D | None = None
    boundary_exit_probability: float | None = None
    if domain is not None:
        outside = ~domain.contains(positions.reshape(-1, 2)).reshape(positions.shape[0], positions.shape[1])
        boundary_violation_probability_over_time = np.mean(outside, axis=0).astype(np.float64)
        boundary_exit_probability = float(np.mean(np.any(outside, axis=1)))

    return MonteCarloMetrics(
        mean_trajectory=mean_trajectory,
        speed_magnitude=speed_magnitude,
        mean_speed_magnitude=mean_speed_magnitude,
        displacement=displacement,
        mean_displacement=mean_displacement,
        position_covariance=position_covariance,
        area_probability_over_time=area_probability_over_time,
        area_hit_probability=area_hit_probability,
        boundary_violation_probability_over_time=boundary_violation_probability_over_time,
        boundary_exit_probability=boundary_exit_probability,
    )


def scalar_summary(metrics: MonteCarloMetrics) -> dict[str, float]:
    out: dict[str, float] = {
        "final_mean_speed": float(metrics.mean_speed_magnitude[-1]),
        "final_mean_displacement": float(metrics.mean_displacement[-1]),
        "final_position_var_x": float(metrics.position_covariance[-1, 0, 0]),
        "final_position_var_y": float(metrics.position_covariance[-1, 1, 1]),
        "final_position_cov_xy": float(metrics.position_covariance[-1, 0, 1]),
    }
    if metrics.area_hit_probability is not None:
        out["area_hit_probability"] = float(metrics.area_hit_probability)
    if metrics.boundary_exit_probability is not None:
        out["boundary_exit_probability"] = float(metrics.boundary_exit_probability)
    return out
