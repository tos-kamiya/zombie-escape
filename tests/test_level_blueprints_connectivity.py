from __future__ import annotations

from zombie_escape.level_blueprints import (
    generate_random_blueprint,
    validate_car_connectivity,
    validate_connectivity,
    validate_humanoid_connectivity,
)
from zombie_escape.models import FuelMode
from zombie_escape.entities_constants import MovingFloorDirection
from zombie_escape.rng import seed_rng


def test_validate_car_connectivity_blocks_pitfalls() -> None:
    grid = [
        "BBBBB",
        "B.C.B",
        "BxxxB",
        "B..EB",
        "BBBBB",
    ]

    assert validate_car_connectivity(grid) is None


def test_validate_car_connectivity_blocks_reinforced_walls() -> None:
    grid = [
        "BBBBB",
        "B.C.B",
        "BRRRB",
        "B..EB",
        "BBBBB",
    ]

    assert validate_car_connectivity(grid) is None


def test_validate_humanoid_connectivity_requires_all_floor_reachable() -> None:
    grid = [
        "BBBBB",
        "B.P.B",
        "BxxxB",
        "B..EB",
        "BBBBB",
    ]

    assert validate_humanoid_connectivity(grid) is False


def test_validate_connectivity_returns_reachable_cells_when_valid() -> None:
    grid = [
        "BBBBB",
        "B.CEB",
        "B...B",
        "B.P.B",
        "BBBBB",
    ]

    reachable = validate_connectivity(grid)
    assert reachable is not None
    assert (3, 1) in reachable  # exit cell


def test_validate_car_connectivity_allows_moving_floor_cells() -> None:
    grid = [
        "BBBBBBB",
        "B.C...B",
        "B^^^^^B",
        "B..E..B",
        "BBBBBBB",
    ]

    reachable = validate_car_connectivity(grid)
    assert reachable is not None
    assert (3, 3) in reachable  # exit cell


def test_validate_humanoid_connectivity_treats_moving_floor_as_blocked() -> None:
    grid = [
        "BBBBBBB",
        "B.P...B",
        "B^^^^^B",
        "B..E..B",
        "BBBBBBB",
    ]

    assert validate_humanoid_connectivity(grid) is False


def test_validate_connectivity_requires_reachable_fuel_when_enabled() -> None:
    grid = [
        "BBBBBBB",
        "BP....B",
        "BxxxxBB",
        "Bf.CE.B",
        "BBBBBBB",
    ]

    assert validate_connectivity(grid, fuel_mode=FuelMode.FUEL_CAN) is None


def test_validate_connectivity_non_fuel_treats_player_as_fuel_start() -> None:
    grid = [
        "BBBBBBB",
        "BP.CE.B",
        "B.....B",
        "BBBBBBB",
    ]

    reachable = validate_connectivity(grid, fuel_mode=FuelMode.START_FULL)
    assert reachable is not None


def test_validate_connectivity_refuel_requires_reachable_empty_can() -> None:
    grid = [
        "BBBBBBBBB",
        "BP.C...EB",
        "B...f...B",
        "BBBBBBBBB",
    ]

    assert (
        validate_connectivity(grid, fuel_mode=FuelMode.REFUEL_CHAIN) is None
    )


def test_validate_connectivity_refuel_respects_one_way_flow() -> None:
    # Player can reach empty can and station, but cannot return from the right side to car
    # because the one-way floor cell '>' blocks leftward movement across the chokepoint.
    grid = [
        "BBBBBBBBBBB",
        "B.PeC>..fEB",
        "BBBBBBBBBBB",
    ]

    assert (
        validate_connectivity(grid, fuel_mode=FuelMode.REFUEL_CHAIN) is None
    )


def test_generate_random_blueprint_allows_puddle_density_on_fall_spawn_zone() -> None:
    seed_rng(12345)
    baseline = generate_random_blueprint(
        steel_chance=0.0,
        cols=10,
        rows=10,
        wall_algo="empty",
        puddle_density=1.0,
        fuel_count=0,
        empty_fuel_can_count=0,
        fuel_station_count=0,
        flashlight_count=0,
        shoes_count=0,
    )
    target = None
    for y, row in enumerate(baseline.grid):
        for x, ch in enumerate(row):
            if ch == "w":
                target = (x, y)
                break
        if target is not None:
            break
    assert target is not None

    seed_rng(12345)
    with_fall_zone = generate_random_blueprint(
        steel_chance=0.0,
        cols=10,
        rows=10,
        wall_algo="empty",
        puddle_density=1.0,
        fall_spawn_zones=[(target[0], target[1], 1, 1)],
        fuel_count=0,
        empty_fuel_can_count=0,
        fuel_station_count=0,
        flashlight_count=0,
        shoes_count=0,
    )

    # Puddle density is allowed to overlap a configured fall-spawn zone.
    assert with_fall_zone.grid[target[1]][target[0]] == "w"


def test_generate_random_blueprint_reinforced_wall_density_skips_moving_floor() -> None:
    seed_rng(12345)
    blueprint = generate_random_blueprint(
        steel_chance=0.0,
        cols=10,
        rows=10,
        wall_algo="empty",
        reinforced_wall_density=1.0,
        moving_floor_cells={(5, 5): MovingFloorDirection.UP},
        fuel_count=0,
        empty_fuel_can_count=0,
        fuel_station_count=0,
        flashlight_count=0,
        shoes_count=0,
    )

    # Reinforced walls should not overwrite moving-floor cells.
    assert blueprint.grid[5][5] == "^"
