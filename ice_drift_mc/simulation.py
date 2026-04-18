from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .model import DriftModelConfig, ForcingInput, as_state_vector, resolve_forcing

Array3D = NDArray[np.float64]
Array2D = NDArray[np.float64]


def simulate_trajectory(
    *,
    initial_state: NDArray[np.float64] | list[float] | tuple[float, ...],
    config: DriftModelConfig,
    wind: ForcingInput,
    current: ForcingInput,
    seed: int | None = None,
) -> Array2D:
    ensemble = simulate_ensemble(
        initial_state=initial_state,
        config=config,
        wind=wind,
        current=current,
        n_simulations=1,
        seed=seed,
    )
    return ensemble[0]


def simulate_ensemble(
    *,
    initial_state: NDArray[np.float64] | list[float] | tuple[float, ...],
    config: DriftModelConfig,
    wind: ForcingInput,
    current: ForcingInput,
    n_simulations: int,
    seed: int | None = None,
) -> Array3D:
    if n_simulations <= 0:
        raise ValueError("n_simulations must be positive")

    n_steps = config.n_steps
    state0 = as_state_vector(initial_state)

    wind_series = resolve_forcing(wind, n_steps=n_steps, dt=config.dt)
    current_series = resolve_forcing(current, n_steps=n_steps, dt=config.dt)

    rng_seed = config.seed if seed is None else seed
    rng = np.random.default_rng(rng_seed)

    trajectories = np.zeros((n_simulations, n_steps + 1, 4), dtype=np.float64)
    trajectories[:, 0, :] = state0.reshape(1, 4)

    position = np.repeat(state0[:2].reshape(1, 2), repeats=n_simulations, axis=0)
    velocity = np.repeat(state0[2:].reshape(1, 2), repeats=n_simulations, axis=0)

    for step in range(n_steps):
        noise = rng.multivariate_normal(mean=np.zeros(2, dtype=np.float64), cov=config.noise_cov, size=n_simulations)
        forcing = config.wind_weight * wind_series[step] + config.current_weight * current_series[step]

        if config.mode == "inertial":
            inertia = max(0.0, 1.0 - config.drag * config.dt)
            velocity = inertia * velocity + forcing.reshape(1, 2) + noise
        else:
            velocity = forcing.reshape(1, 2) + noise

        position = position + velocity * config.dt

        trajectories[:, step + 1, :2] = position
        trajectories[:, step + 1, 2:] = velocity

    return trajectories
