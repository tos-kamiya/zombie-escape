from __future__ import annotations

from collections import deque

import pytest

from zombie_escape.entities_constants import MovingFloorDirection
from zombie_escape.level_blueprints import (
    generate_random_blueprint,
    validate_car_connectivity,
)
from zombie_escape.level_constants import DEFAULT_STEEL_BEAM_CHANCE
from zombie_escape.models import FuelMode
from zombie_escape.rng import seed_rng
from zombie_escape.stage_constants import STAGES


def _expand_zone_cells(
    zones: list[tuple[int, int, int, int]],
    *,
    grid_cols: int,
    grid_rows: int,
) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for col, row, width, height in zones:
        if width <= 0 or height <= 0:
            continue
        start_x = max(0, col)
        start_y = max(0, row)
        end_x = min(grid_cols, col + width)
        end_y = min(grid_rows, row + height)
        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                cells.add((x, y))
    return cells


def _moving_floor_cells_for_stage(
    stage: object,
) -> dict[tuple[int, int], MovingFloorDirection]:
    directions: dict[str, MovingFloorDirection] = {
        "u": MovingFloorDirection.UP,
        "up": MovingFloorDirection.UP,
        "d": MovingFloorDirection.DOWN,
        "down": MovingFloorDirection.DOWN,
        "l": MovingFloorDirection.LEFT,
        "left": MovingFloorDirection.LEFT,
        "r": MovingFloorDirection.RIGHT,
        "right": MovingFloorDirection.RIGHT,
    }
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection] = {}

    zones = getattr(stage, "moving_floor_zones", {})
    for key, zone_list in zones.items():
        direction = directions.get(str(key).lower())
        if direction is None:
            continue
        for cell in _expand_zone_cells(
            zone_list,
            grid_cols=stage.grid_cols,
            grid_rows=stage.grid_rows,
        ):
            moving_floor_cells[cell] = direction

    explicit_cells = getattr(stage, "moving_floor_cells", {})
    for cell, direction in explicit_cells.items():
        try:
            moving_floor_cells[cell] = (
                direction
                if isinstance(direction, MovingFloorDirection)
                else MovingFloorDirection(direction)
            )
        except ValueError:
            continue

    return moving_floor_cells


def _find_cells(grid: list[str], token: str) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch == token:
                cells.append((x, y))
    return cells


def _humanoid_reachable_cells(
    grid: list[str],
    start: tuple[int, int],
) -> set[tuple[int, int]]:
    rows = len(grid)
    cols = len(grid[0])
    passable_cells = {
        (x, y) for y in range(rows) for x in range(cols) if grid[y][x] not in ("x", "B")
    }
    if start not in passable_cells:
        return set()

    floor_blocked_offsets: dict[str, set[tuple[int, int]]] = {
        "^": {(0, 1), (-1, 1), (1, 1)},
        "v": {(0, -1), (-1, -1), (1, -1)},
        "<": {(1, 0), (1, -1), (1, 1)},
        ">": {(-1, 0), (-1, -1), (-1, 1)},
    }
    neighbor_offsets = (
        (0, 1),
        (0, -1),
        (1, 0),
        (-1, 0),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    )

    reachable = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        blocked_offsets = floor_blocked_offsets.get(grid[y][x], set())
        for dx, dy in neighbor_offsets:
            if (dx, dy) in blocked_offsets:
                continue
            nx, ny = x + dx, y + dy
            next_cell = (nx, ny)
            if next_cell in passable_cells and next_cell not in reachable:
                reachable.add(next_cell)
                queue.append(next_cell)

    return reachable


def _build_valid_blueprint_grid(stage: object, *, base_seed: int) -> list[str]:
    moving_floor_cells = _moving_floor_cells_for_stage(stage)
    fuel_count = 0
    empty_fuel_can_count = 0
    fuel_station_count = 0
    if stage.fuel_mode < FuelMode.START_FULL:
        if stage.fuel_mode == FuelMode.REFUEL_CHAIN:
            empty_fuel_can_count = max(1, int(stage.empty_fuel_can_spawn_count))
            fuel_station_count = max(1, int(stage.fuel_station_spawn_count))
        else:
            fuel_count = int(stage.fuel_spawn_count)

    for attempt in range(20):
        seed_rng(base_seed + attempt)
        blueprint = generate_random_blueprint(
            steel_chance=DEFAULT_STEEL_BEAM_CHANCE,
            cols=stage.grid_cols,
            rows=stage.grid_rows,
            exit_sides=stage.exit_sides,
            wall_algo=stage.wall_algorithm,
            pitfall_density=stage.pitfall_density,
            pitfall_zones=stage.pitfall_zones,
            moving_floor_cells=moving_floor_cells,
            fuel_count=fuel_count,
            empty_fuel_can_count=empty_fuel_can_count,
            fuel_station_count=fuel_station_count,
            flashlight_count=int(stage.flashlight_spawn_count),
            shoes_count=int(stage.shoes_spawn_count),
        )
        if validate_car_connectivity(blueprint.grid) is not None:
            return blueprint.grid

    pytest.fail(
        f"Could not build a car-reachable blueprint for {stage.id} in 20 attempts"
    )


@pytest.mark.parametrize("stage", STAGES, ids=[stage.id for stage in STAGES])
def test_stage_blueprint_reachability(stage: object) -> None:
    base_seed = sum(ord(ch) for ch in stage.id) * 1000
    grid = _build_valid_blueprint_grid(stage, base_seed=base_seed)

    player_cells = _find_cells(grid, "P")
    car_cells = _find_cells(grid, "C")
    exit_cells = _find_cells(grid, "E")
    fuel_cells = _find_cells(grid, "f")
    empty_fuel_can_cells = _find_cells(grid, "e")

    assert len(player_cells) == 1
    assert len(car_cells) >= 1
    assert len(exit_cells) >= 1

    player_start = player_cells[0]
    humanoid_from_player = _humanoid_reachable_cells(grid, player_start)

    if stage.fuel_mode == FuelMode.REFUEL_CHAIN:
        assert empty_fuel_can_cells, (
            f"{stage.id}: refuel chain requires empty-can cells"
        )
        assert fuel_cells, f"{stage.id}: refuel chain requires station cells"
        empty_candidates = [
            cell for cell in empty_fuel_can_cells if cell in humanoid_from_player
        ]
        assert empty_candidates, (
            f"{stage.id}: player cannot reach any empty-can candidate"
        )
        can_reach_car_after_refuel = False
        for empty_cell in empty_candidates:
            humanoid_from_empty = _humanoid_reachable_cells(grid, empty_cell)
            station_candidates = [
                cell for cell in fuel_cells if cell in humanoid_from_empty
            ]
            for station_cell in station_candidates:
                humanoid_from_station = _humanoid_reachable_cells(grid, station_cell)
                if any(car_cell in humanoid_from_station for car_cell in car_cells):
                    can_reach_car_after_refuel = True
                    break
            if can_reach_car_after_refuel:
                break
        assert can_reach_car_after_refuel, (
            f"{stage.id}: no valid chain P->e->f->C found for refuel objective"
        )
    elif stage.fuel_mode == FuelMode.FUEL_CAN:
        assert fuel_cells, f"{stage.id}: requires fuel but no fuel cell exists"
        reachable_fuels = [cell for cell in fuel_cells if cell in humanoid_from_player]
        assert reachable_fuels, f"{stage.id}: player cannot reach any fuel cell"

        can_reach_car_from_fuel = False
        for fuel_cell in reachable_fuels:
            humanoid_from_fuel = _humanoid_reachable_cells(grid, fuel_cell)
            if any(car_cell in humanoid_from_fuel for car_cell in car_cells):
                can_reach_car_from_fuel = True
                break
        assert can_reach_car_from_fuel, (
            f"{stage.id}: no reachable fuel cell can lead to a car cell"
        )
    else:
        assert any(car_cell in humanoid_from_player for car_cell in car_cells), (
            f"{stage.id}: player cannot reach any car cell"
        )

    car_reachable = validate_car_connectivity(grid)
    assert car_reachable is not None
    assert any(exit_cell in car_reachable for exit_cell in exit_cells), (
        f"{stage.id}: car cannot reach any exit cell"
    )
