from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from numpy.typing import NDArray

from .model import RectRegion

Array3D = NDArray[np.float64]
Array2D = NDArray[np.float64]


def _draw_region(ax: Axes, region: RectRegion, *, edge_color: str, face_color: str = "none", linestyle: str = "--") -> None:
    rect = Rectangle(
        (region.x_min, region.y_min),
        region.x_max - region.x_min,
        region.y_max - region.y_min,
        linewidth=1.4,
        edgecolor=edge_color,
        facecolor=face_color,
        linestyle=linestyle,
    )
    ax.add_patch(rect)


def plot_trajectories(
    trajectories: Array3D,
    *,
    mean_trajectory: Array2D | None = None,
    sample_size: int = 200,
    domain: RectRegion | None = None,
    target_area: RectRegion | None = None,
    ax: Axes | None = None,
) -> Axes:
    if trajectories.ndim != 3 or trajectories.shape[2] != 4:
        raise ValueError(f"trajectories must have shape (N, S, 4), got {trajectories.shape}")

    if ax is None:
        _, ax = plt.subplots(figsize=(8, 7))

    n_sim = trajectories.shape[0]
    if n_sim <= sample_size:
        subset = trajectories
    else:
        idx = np.linspace(0, n_sim - 1, sample_size, dtype=int)
        subset = trajectories[idx]

    for tr in subset:
        ax.plot(tr[:, 0], tr[:, 1], color="tab:blue", alpha=0.16, linewidth=0.9)

    if mean_trajectory is not None:
        ax.plot(mean_trajectory[:, 0], mean_trajectory[:, 1], color="tab:red", linewidth=2.3, label="Mean trajectory")

    start = trajectories[0, 0, :2]
    ax.scatter(start[0], start[1], color="black", s=35, zorder=4, label="Start")

    if domain is not None:
        _draw_region(ax, domain, edge_color="tab:gray", face_color="none", linestyle="-")
    if target_area is not None:
        _draw_region(ax, target_area, edge_color="tab:green", face_color="none", linestyle="--")

    ax.set_title("Monte Carlo Ice Drift Trajectories")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    return ax


def plot_final_points(
    trajectories: Array3D,
    *,
    domain: RectRegion | None = None,
    target_area: RectRegion | None = None,
    ax: Axes | None = None,
) -> Axes:
    if trajectories.ndim != 3 or trajectories.shape[2] != 4:
        raise ValueError(f"trajectories must have shape (N, S, 4), got {trajectories.shape}")

    if ax is None:
        _, ax = plt.subplots(figsize=(8, 7))

    final_points = trajectories[:, -1, :2]
    mean_point = np.mean(final_points, axis=0)

    ax.scatter(final_points[:, 0], final_points[:, 1], color="tab:purple", s=12, alpha=0.35, label="Final points")
    ax.scatter(mean_point[0], mean_point[1], color="tab:red", s=60, marker="x", label="Mean final point")

    if domain is not None:
        _draw_region(ax, domain, edge_color="tab:gray", face_color="none", linestyle="-")
    if target_area is not None:
        _draw_region(ax, target_area, edge_color="tab:green", face_color="none", linestyle="--")

    ax.set_title("Final Position Cloud")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    return ax


def create_overview_figure(
    trajectories: Array3D,
    *,
    mean_trajectory: Array2D,
    domain: RectRegion | None = None,
    target_area: RectRegion | None = None,
    sample_size: int = 200,
) -> Figure:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    plot_trajectories(
        trajectories,
        mean_trajectory=mean_trajectory,
        sample_size=sample_size,
        domain=domain,
        target_area=target_area,
        ax=axes[0],
    )
    plot_final_points(
        trajectories,
        domain=domain,
        target_area=target_area,
        ax=axes[1],
    )
    return fig
