from __future__ import annotations

from typing import Protocol

from .entities_constants import PUDDLE_SPEED_FACTOR


class HouseplantLike(Protocol):
    x: float
    y: float
    collision_radius: float

    def alive(self) -> bool: ...


def is_in_puddle_cell(
    x: float,
    y: float,
    *,
    cell_size: int,
    puddle_cells: set[tuple[int, int]],
) -> bool:
    if cell_size <= 0 or not puddle_cells:
        return False
    cell = (int(x // cell_size), int(y // cell_size))
    return cell in puddle_cells


def is_touching_houseplant(
    x: float,
    y: float,
    collision_radius: float,
    *,
    cell_size: int,
    houseplants: dict[tuple[int, int], HouseplantLike] | None,
) -> bool:
    if not houseplants or cell_size <= 0:
        return False
    center_cell = (int(x // cell_size), int(y // cell_size))
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            houseplant = houseplants.get((center_cell[0] + dx, center_cell[1] + dy))
            if not houseplant or not houseplant.alive():
                continue
            diff_x = x - houseplant.x
            diff_y = y - houseplant.y
            max_dist = collision_radius + houseplant.collision_radius
            if diff_x * diff_x + diff_y * diff_y <= max_dist * max_dist:
                return True
    return False


def resolve_surface_speed_factor(
    x: float,
    y: float,
    collision_radius: float,
    *,
    cell_size: int,
    puddle_cells: set[tuple[int, int]],
    houseplants: dict[tuple[int, int], HouseplantLike] | None = None,
    houseplant_speed_factor: float = 1.0,
    puddle_speed_factor: float = PUDDLE_SPEED_FACTOR,
) -> float:
    if is_touching_houseplant(
        x,
        y,
        collision_radius,
        cell_size=cell_size,
        houseplants=houseplants,
    ):
        return houseplant_speed_factor
    if is_in_puddle_cell(
        x,
        y,
        cell_size=cell_size,
        puddle_cells=puddle_cells,
    ):
        return puddle_speed_factor
    return 1.0
