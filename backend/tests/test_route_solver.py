import numpy as np

from app.route_solver import solve_astar


def test_astar_returns_route_and_alternative_cost_is_higher_with_corridor_penalty() -> None:
    h, w = 60, 80
    cost = np.ones((h, w), dtype=np.float32)
    conf = np.ones((h, w), dtype=np.float32) * 0.9

    # Create a high-cost obstacle with a narrow corridor.
    cost[20:40, 30:50] = 9999.0
    cost[28:32, 30:50] = 1.5

    bounds = [30.0, 70.0, 40.0, 80.0]

    primary = solve_astar(
        cost_grid=cost,
        confidence_grid=conf,
        bounds=bounds,
        start_lon=30.2,
        start_lat=79.8,
        end_lon=39.8,
        end_lat=70.2,
        vessel_class="Arc7",
        confidence_penalty=2.0,
    )

    alt = solve_astar(
        cost_grid=cost,
        confidence_grid=conf,
        bounds=bounds,
        start_lon=30.2,
        start_lat=79.8,
        end_lon=39.8,
        end_lat=70.2,
        vessel_class="Arc7",
        confidence_penalty=2.0,
        corridor_paths=[primary.path_cells],
    )

    assert len(primary.path_cells) > 2
    assert len(alt.path_cells) > 2
    assert alt.total_cost >= primary.total_cost
