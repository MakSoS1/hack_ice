from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from ice_drift_mc.service import find_default_route_grid, run_drift_forecast


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Monte Carlo ice drift forecast from hack_ice repository")
    parser.add_argument("--route-grid", type=Path, default=None)
    parser.add_argument("--n-sim", type=int, default=2000)
    parser.add_argument("--horizon", type=float, default=24.0)
    parser.add_argument("--dt", type=float, default=1.0)
    parser.add_argument("--mode", type=str, choices=["inertial", "overdamped"], default="inertial")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-fig", type=Path, default=ROOT / "storage" / "reports" / "ice_drift_mc_example.png")
    parser.add_argument("--out-json", type=Path, default=ROOT / "storage" / "reports" / "ice_drift_mc_metrics.json")
    parser.add_argument("--out-trajectories", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    route_grid_path = args.route_grid or find_default_route_grid(ROOT)

    result = run_drift_forecast(
        route_grid_path=route_grid_path,
        n_simulations=int(args.n_sim),
        horizon=float(args.horizon),
        dt=float(args.dt),
        mode=str(args.mode),
        seed=int(args.seed),
        figure_path=args.out_fig,
        metrics_path=args.out_json,
        trajectories_path=args.out_trajectories,
    )

    print(f"route_grid={route_grid_path}")
    if result.figure_path is not None:
        print(f"saved_figure={result.figure_path}")
    if result.metrics_path is not None:
        print(f"saved_metrics={result.metrics_path}")
    if result.trajectories_path is not None:
        print(f"saved_trajectories={result.trajectories_path}")

    for key, value in result.summary.items():
        if isinstance(value, float):
            print(f"{key}={value:.6f}")


if __name__ == "__main__":
    main()
