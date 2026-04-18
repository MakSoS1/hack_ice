# Ice Drift Monte Carlo (2D)

Lightweight Python module for 2D Monte Carlo simulation of ice drift with:
- current vector
- wind vector
- correlated vector noise (`x/y` covariance)

The module is designed for extension to real forcing data (time series and external providers).

## Structure

- `model.py` - config, regions, forcing adapters, typing
- `simulation.py` - one-trajectory and ensemble simulation
- `metrics.py` - scalar and trajectory metrics
- `visualization.py` - trajectory/final cloud plots
- `main.py` - runnable example using existing project data (`storage/layers/*/route_grid.npz`)
- `tests/` - pytest tests

## Dynamics

State vector: `[x, y, vx, vy]`.

- Position update:
  - `x_{t+1}, y_{t+1} = x_t, y_t + dt * v_{t+1}`
- Velocity update supports two modes:
  - `inertial`: keeps momentum (`v_t`) with drag
  - `overdamped`: instantaneous forcing response
- Noise:
  - multivariate normal in velocity space with full `2x2` covariance.

## Metrics

Implemented in `metrics.py`:
- mean trajectory
- speed magnitude
- displacement from initial point
- position covariance over time
- probability of hitting a target area
- probability of crossing domain boundary

## Example run

From repository root:

```bash
python3 -m ice_drift_mc.main --n-sim 2000 --horizon 24 --dt 1 --mode inertial --seed 42
```

Repository-friendly wrapper (same behavior, aligned with existing `ml.*` commands):

```bash
python3 -m ml.drift_forecast --n-sim 2000 --horizon 24 --dt 1 --mode inertial --seed 42
```

Outputs:
- figure: `storage/reports/ice_drift_mc_example.png`
- scalar metrics: `storage/reports/ice_drift_mc_metrics.json`

The example automatically uses existing route-grid data from `storage/layers/*/route_grid.npz`.

## Tests

```bash
pytest -q ice_drift_mc/tests
```

## Extensibility hooks

- forcing can be:
  - constant vector `(2,)`
  - time series `(T, 2)`
  - callable `(step, t) -> (2,)`
- movement mode is configurable (`inertial`, `overdamped`)
- architecture is ready for plugging real wind/current pipelines.
