from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

VESSEL_MULTIPLIER = {
    "Arc4": 2.2,
    "Arc5": 1.9,
    "Arc6": 1.55,
    "Arc7": 1.25,
    "Arc9": 1.0,
}


@dataclass
class GridRoute:
    path_cells: list[tuple[int, int]]
    total_cost: float
    distance_km: float
    risk_score: float
    confidence_score: float


def lonlat_to_cell(lon: float, lat: float, bounds: list[float], shape_hw: tuple[int, int]) -> tuple[int, int]:
    lon_min, lat_min, lon_max, lat_max = bounds
    h, w = shape_hw
    x = int(round((lon - lon_min) / max(1e-9, (lon_max - lon_min)) * (w - 1)))
    y = int(round((lat_max - lat) / max(1e-9, (lat_max - lat_min)) * (h - 1)))
    x = max(0, min(w - 1, x))
    y = max(0, min(h - 1, y))
    return y, x


def cell_to_lonlat(y: int, x: int, bounds: list[float], shape_hw: tuple[int, int]) -> tuple[float, float]:
    lon_min, lat_min, lon_max, lat_max = bounds
    h, w = shape_hw
    lon = lon_min + (x / max(1, w - 1)) * (lon_max - lon_min)
    lat = lat_max - (y / max(1, h - 1)) * (lat_max - lat_min)
    return lon, lat


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0088
    dlon = math.radians(lon2 - lon1)
    dlat = math.radians(lat2 - lat1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    dy = abs(a[0] - b[0])
    dx = abs(a[1] - b[1])
    return math.sqrt(dx * dx + dy * dy)


def _neighbors(y: int, x: int, h: int, w: int) -> Iterable[tuple[int, int, float]]:
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
        ny, nx = y + dy, x + dx
        if 0 <= ny < h and 0 <= nx < w:
            yield ny, nx, math.sqrt(2.0) if dy != 0 and dx != 0 else 1.0


def _reconstruct(came_from: dict[tuple[int, int], tuple[int, int]], current: tuple[int, int]) -> list[tuple[int, int]]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def route_stats_for_path(
    path: list[tuple[int, int]],
    bounds: list[float],
    shape_hw: tuple[int, int],
    cost_grid: np.ndarray,
    confidence_grid: np.ndarray,
) -> tuple[float, float, float]:
    if len(path) < 2:
        return 0.0, 0.0, 0.0

    total_km = 0.0
    costs = []
    confs = []
    prev_lon, prev_lat = cell_to_lonlat(path[0][0], path[0][1], bounds, shape_hw)
    for y, x in path:
        lon, lat = cell_to_lonlat(y, x, bounds, shape_hw)
        total_km += haversine_km(prev_lon, prev_lat, lon, lat)
        prev_lon, prev_lat = lon, lat
        costs.append(float(cost_grid[y, x]))
        confs.append(float(confidence_grid[y, x]))

    risk = float(np.mean(costs)) if costs else 0.0
    conf = float(np.mean(confs)) if confs else 0.0
    return total_km, risk, conf


def solve_astar(
    cost_grid: np.ndarray,
    confidence_grid: np.ndarray,
    bounds: list[float],
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
    vessel_class: str,
    confidence_penalty: float,
    corridor_paths: list[list[tuple[int, int]]] | None = None,
) -> GridRoute:
    if cost_grid.ndim != 2:
        raise ValueError("cost_grid must be 2D")

    h, w = cost_grid.shape
    start = lonlat_to_cell(start_lon, start_lat, bounds, (h, w))
    goal = lonlat_to_cell(end_lon, end_lat, bounds, (h, w))
    if start == goal:
        raise RuntimeError("Start and end points collapse to the same route cell for this layer bounds")

    multiplier = VESSEL_MULTIPLIER.get(vessel_class, VESSEL_MULTIPLIER["Arc7"])
    blocked_threshold = 8000.0

    working_cost = cost_grid.astype(np.float32).copy()
    if corridor_paths:
        for alt_idx, path in enumerate(corridor_paths, start=1):
            _apply_corridor_penalty(working_cost, path, radius=5 + alt_idx, factor=1.55 + 0.15 * alt_idx)

    open_heap: list[tuple[float, tuple[int, int]]] = []
    heapq.heappush(open_heap, (0.0, start))

    g_score: dict[tuple[int, int], float] = {start: 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}

    closed: set[tuple[int, int]] = set()

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            path = _reconstruct(came_from, current)
            dist_km, risk_score, conf_score = route_stats_for_path(path, bounds, (h, w), cost_grid, confidence_grid)
            return GridRoute(
                path_cells=path,
                total_cost=float(g_score[current]),
                distance_km=dist_km,
                risk_score=risk_score,
                confidence_score=conf_score,
            )

        closed.add(current)
        cy, cx = current
        for ny, nx, step_len in _neighbors(cy, cx, h, w):
            if (ny, nx) in closed:
                continue

            cell_cost = float(working_cost[ny, nx])
            if cell_cost >= blocked_threshold:
                continue

            conf_pen = confidence_penalty * float(1.0 - confidence_grid[ny, nx])
            transition = step_len * (cell_cost * multiplier + conf_pen)
            tentative = g_score[current] + transition

            if tentative < g_score.get((ny, nx), float("inf")):
                g_score[(ny, nx)] = tentative
                came_from[(ny, nx)] = current
                f = tentative + _heuristic((ny, nx), goal)
                heapq.heappush(open_heap, (f, (ny, nx)))

    raise RuntimeError("No valid route found for given endpoints and constraints")


def _apply_corridor_penalty(cost_grid: np.ndarray, path: list[tuple[int, int]], radius: int, factor: float) -> None:
    h, w = cost_grid.shape
    for y, x in path:
        y0 = max(0, y - radius)
        y1 = min(h, y + radius + 1)
        x0 = max(0, x - radius)
        x1 = min(w, x + radius + 1)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        dist = np.sqrt((yy - y) ** 2 + (xx - x) ** 2)
        mask = dist <= radius
        decay = 1.0 + (factor - 1.0) * (1.0 - dist / max(1, radius))
        window = cost_grid[y0:y1, x0:x1]
        window[mask] *= decay[mask]


def downsample_grid(arr: np.ndarray, out_hw: tuple[int, int], mode: str = "nearest") -> np.ndarray:
    out_h, out_w = out_hw
    in_h, in_w = arr.shape[:2]
    if out_h == in_h and out_w == in_w:
        return arr

    yy = np.linspace(0, in_h - 1, out_h).astype(np.int32)
    xx = np.linspace(0, in_w - 1, out_w).astype(np.int32)

    if mode == "nearest":
        return arr[np.ix_(yy, xx)]

    raise ValueError(f"Unsupported mode={mode}")
