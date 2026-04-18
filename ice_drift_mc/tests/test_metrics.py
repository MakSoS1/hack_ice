from __future__ import annotations

import numpy as np

from ice_drift_mc.metrics import compute_metrics
from ice_drift_mc.model import RectRegion


def test_metrics_probabilities_for_area_and_boundary() -> None:
    # shape: (N=2, S=3, state=4)
    traj = np.array(
        [
            [
                [0.0, 0.0, 0.0, 0.0],
                [2.0, 2.0, 1.0, 1.0],
                [4.0, 4.0, 1.0, 1.0],
            ],
            [
                [0.0, 0.0, 0.0, 0.0],
                [8.0, 8.0, 1.0, 1.0],
                [11.0, 8.0, 1.0, 0.0],
            ],
        ],
        dtype=np.float64,
    )

    target = RectRegion(x_min=1.0, y_min=1.0, x_max=3.0, y_max=3.0)
    domain = RectRegion(x_min=0.0, y_min=0.0, x_max=10.0, y_max=10.0)

    m = compute_metrics(traj, target_area=target, domain=domain)

    assert m.area_probability_over_time is not None
    assert m.boundary_violation_probability_over_time is not None
    assert m.area_hit_probability is not None
    assert m.boundary_exit_probability is not None

    np.testing.assert_allclose(m.area_probability_over_time, np.array([0.0, 0.5, 0.0]))
    np.testing.assert_allclose(m.boundary_violation_probability_over_time, np.array([0.0, 0.0, 0.5]))
    assert abs(m.area_hit_probability - 0.5) < 1e-12
    assert abs(m.boundary_exit_probability - 0.5) < 1e-12


def test_position_covariance_shape() -> None:
    traj = np.zeros((10, 6, 4), dtype=np.float64)
    # linearly spread points to make covariance non-zero
    for i in range(10):
        traj[i, :, 0] = i
        traj[i, :, 1] = -i

    m = compute_metrics(traj)
    assert m.position_covariance.shape == (6, 2, 2)
    assert np.all(m.position_covariance[:, 0, 0] >= 0.0)
    assert np.all(m.position_covariance[:, 1, 1] >= 0.0)
