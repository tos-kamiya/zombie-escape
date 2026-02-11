from __future__ import annotations

from zombie_escape.level_blueprints import (
    validate_car_connectivity,
    validate_connectivity,
    validate_humanoid_connectivity,
)


def test_validate_car_connectivity_blocks_pitfalls() -> None:
    grid = [
        "BBBBB",
        "B.C.B",
        "BxxxB",
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


def test_validate_car_connectivity_treats_moving_floor_as_blocked() -> None:
    grid = [
        "BBBBBBB",
        "B.C...B",
        "B^^^^^B",
        "B..E..B",
        "BBBBBBB",
    ]

    assert validate_car_connectivity(grid) is None


def test_validate_humanoid_connectivity_treats_moving_floor_as_blocked() -> None:
    grid = [
        "BBBBBBB",
        "B.P...B",
        "B^^^^^B",
        "B..E..B",
        "BBBBBBB",
    ]

    assert validate_humanoid_connectivity(grid) is False
