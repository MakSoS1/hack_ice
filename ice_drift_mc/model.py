from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

import numpy as np
from numpy.typing import NDArray

Vec2 = NDArray[np.float64]
StateVector = NDArray[np.float64]
Array2D = NDArray[np.float64]
MovementMode = Literal["inertial", "overdamped"]
ForcingProvider = Callable[[int, float], Vec2]
ForcingInput = Vec2 | Array2D | ForcingProvider


@dataclass(frozen=True)
class RectRegion:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        if self.x_min >= self.x_max:
            raise ValueError("x_min must be smaller than x_max")
        if self.y_min >= self.y_max:
            raise ValueError("y_min must be smaller than y_max")

    def contains(self, points: Array2D) -> NDArray[np.bool_]:
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError(f"points must have shape (N, 2), got {points.shape}")
        return (
            (points[:, 0] >= self.x_min)
            & (points[:, 0] <= self.x_max)
            & (points[:, 1] >= self.y_min)
            & (points[:, 1] <= self.y_max)
        )


@dataclass(frozen=True)
class DriftModelConfig:
    horizon: float
    dt: float
    drag: float = 0.08
    wind_weight: float = 0.35
    current_weight: float = 0.85
    noise_cov: Array2D = field(default_factory=lambda: np.array([[0.02, 0.0], [0.0, 0.02]], dtype=np.float64))
    mode: MovementMode = "inertial"
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.horizon <= 0.0:
            raise ValueError("horizon must be positive")
        if self.dt <= 0.0:
            raise ValueError("dt must be positive")
        if self.drag < 0.0:
            raise ValueError("drag must be non-negative")
        if self.mode not in {"inertial", "overdamped"}:
            raise ValueError(f"Unsupported mode={self.mode}")
        cov = np.asarray(self.noise_cov, dtype=np.float64)
        if cov.shape != (2, 2):
            raise ValueError(f"noise_cov must have shape (2, 2), got {cov.shape}")
        if not np.allclose(cov, cov.T, atol=1e-12):
            raise ValueError("noise_cov must be symmetric")
        eigvals = np.linalg.eigvalsh(cov)
        if np.any(eigvals < -1e-12):
            raise ValueError("noise_cov must be positive semi-definite")

    @property
    def n_steps(self) -> int:
        return int(np.round(self.horizon / self.dt))


def as_state_vector(state: StateVector | list[float] | tuple[float, ...]) -> StateVector:
    arr = np.asarray(state, dtype=np.float64)
    if arr.shape != (4,):
        raise ValueError(f"state must have shape (4,), got {arr.shape}")
    return arr


def resolve_forcing(forcing: ForcingInput, *, n_steps: int, dt: float) -> Array2D:
    if callable(forcing):
        values = np.zeros((n_steps, 2), dtype=np.float64)
        for step in range(n_steps):
            values[step] = np.asarray(forcing(step, step * dt), dtype=np.float64)
        return values

    arr = np.asarray(forcing, dtype=np.float64)
    if arr.shape == (2,):
        return np.repeat(arr.reshape(1, 2), repeats=n_steps, axis=0)

    if arr.ndim == 2 and arr.shape[1] == 2:
        if arr.shape[0] == n_steps:
            return arr.copy()
        if arr.shape[0] == n_steps + 1:
            return arr[:-1].copy()
        raise ValueError(f"Forcing time series must have shape (n_steps, 2) or (n_steps+1, 2), got {arr.shape}")

    raise ValueError("Forcing must be a 2D vector, a (T, 2) time series, or a callable")
