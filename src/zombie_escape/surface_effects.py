from __future__ import annotations

from typing import Protocol

from .entities_constants import PUDDLE_SPEED_FACTOR


class SpikyPlantLike(Protocol):
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


def is_in_contaminated_cell(
    x: float,
    y: float,
    *,
    cell_size: int,
    contaminated_cells: set[tuple[int, int]],
) -> bool:
    if cell_size <= 0 or not contaminated_cells:
        return False
    cell = (int(x // cell_size), int(y // cell_size))
    return cell in contaminated_cells


def is_touching_spiky_plant(
    x: float,
    y: float,
    collision_radius: float,
    *,
    cell_size: int,
    spiky_plants: dict[tuple[int, int], SpikyPlantLike] | None,
) -> bool:
    if not spiky_plants or cell_size <= 0:
        return False
    center_cell = (int(x // cell_size), int(y // cell_size))
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            spiky_plant = spiky_plants.get((center_cell[0] + dx, center_cell[1] + dy))
            if not spiky_plant or not spiky_plant.alive():
                continue
            diff_x = x - spiky_plant.x
            diff_y = y - spiky_plant.y
            max_dist = collision_radius + spiky_plant.collision_radius
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
    spiky_plants: dict[tuple[int, int], SpikyPlantLike] | None = None,
    spiky_plant_speed_factor: float = 1.0,
    puddle_speed_factor: float = PUDDLE_SPEED_FACTOR,
) -> float:
    if is_touching_spiky_plant(
        x,
        y,
        collision_radius,
        cell_size=cell_size,
        spiky_plants=spiky_plants,
    ):
        return spiky_plant_speed_factor
    if is_in_puddle_cell(
        x,
        y,
        cell_size=cell_size,
        puddle_cells=puddle_cells,
    ):
        return puddle_speed_factor
    return 1.0

