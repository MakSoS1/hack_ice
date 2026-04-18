from __future__ import annotations

import argparse
from pathlib import Path

from .service import find_default_route_grid, run_drift_forecast


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monte Carlo ice drift simulation example")
    parser.add_argument("--n-sim", type=int, default=2000)
    parser.add_argument("--horizon", type=float, default=24.0)
    parser.add_argument("--dt", type=float, default=1.0)
    parser.add_argument("--mode", type=str, default="inertial", choices=["inertial", "overdamped"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--route-grid", type=Path, default=None)
    parser.add_argument("--out-fig", type=Path, default=None)
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-trajectories", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    route_grid_path = args.route_grid or find_default_route_grid(repo_root)
    out_fig = args.out_fig or (repo_root / "storage" / "reports" / "ice_drift_mc_example.png")
    out_json = args.out_json or (repo_root / "storage" / "reports" / "ice_drift_mc_metrics.json")
    result = run_drift_forecast(
        route_grid_path=route_grid_path,
        n_simulations=int(args.n_sim),
        horizon=float(args.horizon),
        dt=float(args.dt),
        mode=str(args.mode),
        seed=int(args.seed),
        figure_path=out_fig,
        metrics_path=out_json,
        trajectories_path=args.out_trajectories,
    )
    summary = result.summary

    print(f"saved_figure={out_fig}")
    print(f"saved_metrics={out_json}")
    if args.out_trajectories is not None:
        print(f"saved_trajectories={args.out_trajectories}")
    for key, value in summary.items():
        if isinstance(value, float):
            print(f"{key}={value:.6f}")


if __name__ == "__main__":
    main()
