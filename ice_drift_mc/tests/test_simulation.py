from __future__ import annotations

import numpy as np

from ice_drift_mc.model import DriftModelConfig
from ice_drift_mc.simulation import simulate_ensemble, simulate_trajectory


def test_single_trajectory_shape_and_seed_reproducibility() -> None:
    cfg = DriftModelConfig(
        horizon=4.0,
        dt=1.0,
        mode="inertial",
        seed=123,
        noise_cov=np.zeros((2, 2), dtype=np.float64),
    )
    init = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)

    tr_a = simulate_trajectory(initial_state=init, config=cfg, wind=np.array([1.0, 0.0]), current=np.array([0.0, 0.0]))
    tr_b = simulate_trajectory(initial_state=init, config=cfg, wind=np.array([1.0, 0.0]), current=np.array([0.0, 0.0]))

    assert tr_a.shape == (cfg.n_steps + 1, 4)
    np.testing.assert_allclose(tr_a, tr_b)


def test_noise_covariance_induces_xy_correlation() -> None:
    cfg = DriftModelConfig(
        horizon=1.0,
        dt=1.0,
        mode="overdamped",
        seed=7,
        wind_weight=0.0,
        current_weight=0.0,
        noise_cov=np.array([[1.0, 0.7], [0.7, 1.0]], dtype=np.float64),
    )
    init = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)

    traj = simulate_ensemble(
        initial_state=init,
        config=cfg,
        wind=np.array([0.0, 0.0]),
        current=np.array([0.0, 0.0]),
        n_simulations=4000,
    )
    vel = traj[:, 1, 2:4]
    corr = np.corrcoef(vel[:, 0], vel[:, 1])[0, 1]

    assert corr > 0.55


def test_time_series_forcing_is_supported() -> None:
    cfg = DriftModelConfig(
        horizon=2.0,
        dt=0.5,
        mode="overdamped",
        seed=1,
        wind_weight=1.0,
        current_weight=0.0,
        noise_cov=np.zeros((2, 2), dtype=np.float64),
    )
    init = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)

    wind_series = np.repeat(np.array([[1.0, 0.0]], dtype=np.float64), repeats=cfg.n_steps, axis=0)

    tr = simulate_trajectory(initial_state=init, config=cfg, wind=wind_series, current=np.array([0.0, 0.0]))

    assert abs(float(tr[-1, 0]) - 2.0) < 1e-10
    assert abs(float(tr[-1, 1])) < 1e-10


def test_modes_produce_different_dynamics() -> None:
    base_kwargs = {
        "horizon": 5.0,
        "dt": 1.0,
        "drag": 0.2,
        "seed": 11,
        "wind_weight": 1.0,
        "current_weight": 0.0,
        "noise_cov": np.zeros((2, 2), dtype=np.float64),
    }
    init = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)

    inertial = simulate_trajectory(
        initial_state=init,
        config=DriftModelConfig(mode="inertial", **base_kwargs),
        wind=np.array([1.0, 0.0]),
        current=np.array([0.0, 0.0]),
    )
    overdamped = simulate_trajectory(
        initial_state=init,
        config=DriftModelConfig(mode="overdamped", **base_kwargs),
        wind=np.array([1.0, 0.0]),
        current=np.array([0.0, 0.0]),
    )

    assert float(inertial[-1, 0]) > float(overdamped[-1, 0])
