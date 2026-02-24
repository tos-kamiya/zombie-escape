from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any

import pygame

from ..colors import get_environment_palette
from ..entities import ReinforcedWall, RubbleWall, SteelBeam, Wall
from ..entities_constants import (
    INTERNAL_WALL_BEVEL_DEPTH,
    INTERNAL_WALL_HEALTH,
    MovingFloorDirection,
    STEEL_BEAM_HEALTH,
)
from ..level_constants import DEFAULT_STEEL_BEAM_CHANCE
from ..render_assets import RUBBLE_ROTATION_DEG
from ..render.world_tiles import build_floor_ruin_cells
from .constants import LAYER_WALLS, OUTER_WALL_HEALTH
from ..level_blueprints import (
    Blueprint,
    MapGenerationError,
    generate_random_blueprint,
    validate_connectivity,
)
from ..models import LevelLayout, Stage
from ..models import FuelMode
from ..rng import get_rng, seed_rng

__all__ = ["generate_level_from_blueprint", "MapGenerationError"]

RNG = get_rng()


@dataclass
class _WorldBuildResult:
    outer_wall_cells: set[tuple[int, int]]
    wall_cells: set[tuple[int, int]]
    steel_beam_cells: set[tuple[int, int]]
    outside_cells: set[tuple[int, int]]
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection]
    walkable_cells: list[tuple[int, int]]
    pitfall_cells: set[tuple[int, int]]
    fire_floor_cells: set[tuple[int, int]]
    metal_floor_cells: set[tuple[int, int]]
    spiky_plant_cells: set[tuple[int, int]]
    puddle_cells: set[tuple[int, int]]
    player_cells: list[tuple[int, int]]
    car_cells: list[tuple[int, int]]
    fuel_cells: list[tuple[int, int]]
    empty_fuel_can_cells: list[tuple[int, int]]
    flashlight_cells: list[tuple[int, int]]
    shoes_cells: list[tuple[int, int]]
    bevel_corners: dict[tuple[int, int], tuple[bool, bool, bool, bool]]


def _rect_for_cell(x_idx: int, y_idx: int, cell_size: int) -> pygame.Rect:
    return pygame.Rect(
        x_idx * cell_size,
        y_idx * cell_size,
        cell_size,
        cell_size,
    )


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


def _expand_moving_floor_cells(
    stage: Stage,
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
        "U": MovingFloorDirection.UP,
        "D": MovingFloorDirection.DOWN,
        "L": MovingFloorDirection.LEFT,
        "R": MovingFloorDirection.RIGHT,
    }
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection] = {}
    if stage.moving_floor_zones:
        for key, zones in stage.moving_floor_zones.items():
            direction = directions.get(str(key).lower(), directions.get(str(key)))
            if not direction or not zones:
                continue
            for cell in _expand_zone_cells(
                zones,
                grid_cols=stage.grid_cols,
                grid_rows=stage.grid_rows,
            ):
                moving_floor_cells[cell] = direction
    if stage.moving_floor_cells:
        for cell, direction in stage.moving_floor_cells.items():
            try:
                dir_enum = (
                    direction
                    if isinstance(direction, MovingFloorDirection)
                    else MovingFloorDirection(direction)
                )
            except ValueError:
                continue
            moving_floor_cells[cell] = dir_enum
    return moving_floor_cells


def _filter_spawn_cells(
    cells: list[tuple[int, int]],
    *,
    blocked_cells: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    return [cell for cell in cells if cell not in blocked_cells]


def _build_layout_data(
    *,
    layout: LevelLayout,
    player_cells: list[tuple[int, int]],
    filtered_car_cells: list[tuple[int, int]],
    fuel_cells: list[tuple[int, int]],
    empty_fuel_can_cells: list[tuple[int, int]],
    flashlight_cells: list[tuple[int, int]],
    shoes_cells: list[tuple[int, int]],
    spiky_plant_cells: set[tuple[int, int]],
    fire_floor_cells: set[tuple[int, int]],
    metal_floor_cells: set[tuple[int, int]],
    puddle_cells: set[tuple[int, int]],
    walkable_cells: list[tuple[int, int]],
    car_reachable_cells: set[tuple[int, int]],
    item_spawn_cells: list[tuple[int, int]],
    car_spawn_cells: list[tuple[int, int]],
) -> dict[str, list[tuple[int, int]]]:
    return {
        "player_cells": player_cells,
        "car_cells": filtered_car_cells,
        "fuel_cells": fuel_cells,
        "empty_fuel_can_cells": empty_fuel_can_cells,
        "fuel_station_cells": fuel_cells,
        "flashlight_cells": flashlight_cells,
        "shoes_cells": shoes_cells,
        "spiky_plant_cells": list(spiky_plant_cells),
        "fire_floor_cells": list(fire_floor_cells),
        "metal_floor_cells": list(metal_floor_cells),
        "zombie_contaminated_cells": list(layout.zombie_contaminated_cells),
        "puddle_cells": list(puddle_cells),
        "walkable_cells": walkable_cells,
        "car_walkable_cells": list(car_reachable_cells),
        "item_spawn_cells": item_spawn_cells,
        "car_spawn_cells": list(car_spawn_cells),
    }


def _finalize_layout_cells(
    *,
    stage: Stage,
    layout: LevelLayout,
    walkable_cells: list[tuple[int, int]],
    pitfall_cells: set[tuple[int, int]],
    fire_floor_cells: set[tuple[int, int]],
    metal_floor_cells: set[tuple[int, int]],
    puddle_cells: set[tuple[int, int]],
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection],
    spiky_plant_cells: set[tuple[int, int]],
    car_reachable_cells: set[tuple[int, int]],
    car_cells: list[tuple[int, int]],
    interior_min_x: int,
    interior_max_x: int,
    interior_min_y: int,
    interior_max_y: int,
) -> tuple[
    list[tuple[int, int]],
    list[tuple[int, int]],
    list[tuple[int, int]],
    list[tuple[int, int]],
]:
    if moving_floor_cells:
        movable_floor_cells = [
            cell
            for cell in moving_floor_cells
            if cell not in pitfall_cells and cell not in fire_floor_cells
        ]
        for cell in movable_floor_cells:
            if cell not in walkable_cells:
                walkable_cells.append(cell)
    layout.walkable_cells = walkable_cells
    layout.pitfall_cells = pitfall_cells
    layout.car_walkable_cells = set(car_reachable_cells)
    layout.moving_floor_cells = moving_floor_cells

    fall_spawn_cells = _expand_zone_cells(
        stage.fall_spawn_zones,
        grid_cols=stage.grid_cols,
        grid_rows=stage.grid_rows,
    )
    walkable_set = set(walkable_cells)
    floor_ratio = max(0.0, min(1.0, stage.fall_spawn_cell_ratio))
    if floor_ratio > 0.0 and interior_min_x <= interior_max_x:
        candidates = [
            cell
            for cell in walkable_set
            if (
                interior_min_x <= cell[0] <= interior_max_x
                and interior_min_y <= cell[1] <= interior_max_y
            )
        ]
        if candidates:
            RNG.shuffle(candidates)
            pick_count = max(1, int(round(len(candidates) * floor_ratio)))
            pick_count = min(len(candidates), pick_count)
            fall_spawn_cells.update(candidates[:pick_count])
    layout.fall_spawn_cells = fall_spawn_cells

    floor_ruin_candidates = [
        cell
        for cell in walkable_set
        if cell not in pitfall_cells
        and cell not in fire_floor_cells
        and cell not in metal_floor_cells
        and cell not in puddle_cells
        and cell not in moving_floor_cells
        and cell not in spiky_plant_cells
    ]
    layout.floor_ruin_cells = build_floor_ruin_cells(
        candidate_cells=floor_ruin_candidates,
        rubble_ratio=float(stage.wall_rubble_ratio),
    )

    blocked_spawn_cells = set(fire_floor_cells) | set(moving_floor_cells) | set(
        spiky_plant_cells
    )
    item_spawn_cells = _filter_spawn_cells(
        walkable_cells,
        blocked_cells=blocked_spawn_cells,
    )
    car_spawn_cells = _filter_spawn_cells(
        list(car_reachable_cells),
        blocked_cells=blocked_spawn_cells,
    )
    filtered_car_cells = _filter_spawn_cells(
        list(car_cells),
        blocked_cells=blocked_spawn_cells,
    )
    layout.car_spawn_cells = list(car_spawn_cells)
    return walkable_cells, item_spawn_cells, car_spawn_cells, filtered_car_cells


def _generate_valid_blueprint_with_retries(
    *,
    stage: Stage,
    seed: int | None,
    steel_chance: float,
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection],
    fuel_count: int,
    empty_fuel_can_count: int,
    fuel_station_count: int,
    flashlight_count: int,
    shoes_count: int,
) -> Blueprint:
    for attempt in range(20):
        if seed is not None:
            seed_rng(seed + attempt)
        try:
            blueprint = generate_random_blueprint(
                steel_chance=steel_chance,
                cols=stage.grid_cols,
                rows=stage.grid_rows,
                exit_sides=stage.exit_sides,
                wall_algo=stage.wall_algorithm,
                pitfall_density=stage.pitfall_density,
                pitfall_zones=stage.pitfall_zones,
                fire_floor_density=stage.fire_floor_density,
                fire_floor_zones=stage.fire_floor_zones,
                metal_floor_density=stage.metal_floor_density,
                metal_floor_zones=stage.metal_floor_zones,
                reinforced_wall_density=stage.reinforced_wall_density,
                reinforced_wall_zones=stage.reinforced_wall_zones,
                moving_floor_cells=moving_floor_cells,
                fuel_count=fuel_count,
                empty_fuel_can_count=empty_fuel_can_count,
                fuel_station_count=fuel_station_count,
                flashlight_count=flashlight_count,
                shoes_count=shoes_count,
                spiky_plant_density=stage.spiky_plant_density,
                spiky_plant_zones=stage.spiky_plant_zones,
                puddle_density=stage.puddle_density,
                puddle_zones=stage.puddle_zones,
            )
        except MapGenerationError:
            continue

        require_car_spawn = not stage.endurance_stage
        car_reachable = validate_connectivity(
            blueprint.grid,
            fuel_mode=(
                stage.fuel_mode if not stage.endurance_stage else FuelMode.START_FULL
            ),
            require_player_exit_path=stage.endurance_stage,
            require_car_spawn=require_car_spawn,
        )
        if car_reachable is None:
            continue

        blueprint.car_reachable_cells = car_reachable
        return blueprint

    raise MapGenerationError(
        "Blueprint generation/connectivity validation failed after 20 attempts"
    )


def _build_world_from_blueprint(
    *,
    stage: Stage,
    blueprint: list[str],
    wall_group: pygame.sprite.Group,
    all_sprites: pygame.sprite.LayeredUpdates,
    steel_enabled: bool,
    steel_cells: set[tuple[int, int]],
    ambient_palette_key: str | None,
) -> _WorldBuildResult:
    cell_size = stage.cell_size
    outer_wall_cells = {
        (x, y)
        for y, row in enumerate(blueprint)
        for x, ch in enumerate(row)
        if ch == "B"
    }
    wall_cells = {
        (x, y)
        for y, row in enumerate(blueprint)
        for x, ch in enumerate(row)
        if ch in {"B", "1", "R"}
    }
    steel_beam_cells: set[tuple[int, int]] = set()
    outside_cells: set[tuple[int, int]] = set()
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection] = {}
    walkable_cells: list[tuple[int, int]] = []
    pitfall_cells: set[tuple[int, int]] = set()
    fire_floor_cells: set[tuple[int, int]] = set()
    metal_floor_cells: set[tuple[int, int]] = set()
    spiky_plant_cells: set[tuple[int, int]] = set()
    puddle_cells: set[tuple[int, int]] = set()
    player_cells: list[tuple[int, int]] = []
    car_cells: list[tuple[int, int]] = []
    fuel_cells: list[tuple[int, int]] = []
    empty_fuel_can_cells: list[tuple[int, int]] = []
    flashlight_cells: list[tuple[int, int]] = []
    shoes_cells: list[tuple[int, int]] = []
    bevel_corners: dict[tuple[int, int], tuple[bool, bool, bool, bool]] = {}
    palette = get_environment_palette(ambient_palette_key)
    rubble_ratio = max(0.0, min(1.0, stage.wall_rubble_ratio))

    def _has_wall(nx: int, ny: int) -> bool:
        if nx < 0 or ny < 0 or nx >= stage.grid_cols or ny >= stage.grid_rows:
            return True
        return (nx, ny) in wall_cells

    def remove_steel_beam_cell(cell: tuple[int, int]) -> None:
        if cell in steel_beam_cells:
            steel_beam_cells.discard(cell)
        if (
            cell not in wall_cells
            and cell not in outer_wall_cells
            and cell not in pitfall_cells
            and cell not in walkable_cells
        ):
            walkable_cells.append(cell)

    def add_beam_to_groups(beam: SteelBeam, *, cell: tuple[int, int]) -> None:
        if beam._added_to_groups:
            return
        wall_group.add(beam)
        all_sprites.add(beam, layer=LAYER_WALLS)
        steel_beam_cells.add(cell)
        beam._added_to_groups = True

    def remove_wall_cell(cell: tuple[int, int], *, allow_walkable: bool = True) -> None:
        if cell in wall_cells:
            wall_cells.discard(cell)
            if allow_walkable and cell not in walkable_cells:
                walkable_cells.append(cell)
        outer_wall_cells.discard(cell)

    for y, row in enumerate(blueprint):
        if len(row) != stage.grid_cols:
            raise ValueError(
                f"Blueprint width mismatch at row {y}: {len(row)} != {stage.grid_cols}"
            )
        for x, ch in enumerate(row):
            cell_rect = _rect_for_cell(x, y, cell_size)
            cell_has_beam = steel_enabled and (x, y) in steel_cells
            if ch == "O":
                outside_cells.add((x, y))
                continue
            if ch == "B":
                draw_bottom_side = not _has_wall(x, y + 1)
                wall_cell = (x, y)
                wall = Wall(
                    cell_rect.x,
                    cell_rect.y,
                    cell_rect.width,
                    cell_rect.height,
                    health=OUTER_WALL_HEALTH,
                    palette=palette,
                    palette_category="outer_wall",
                    bevel_depth=0,
                    draw_bottom_side=draw_bottom_side,
                    on_destroy=(lambda _w, cell=wall_cell: remove_wall_cell(cell)),
                )
                wall_group.add(wall)
                all_sprites.add(wall, layer=LAYER_WALLS)
                continue
            if ch == "R":
                draw_bottom_side = not _has_wall(x, y + 1)
                bevel_mask = (
                    not _has_wall(x, y - 1)
                    and not _has_wall(x - 1, y)
                    and not _has_wall(x - 1, y - 1),
                    not _has_wall(x, y - 1)
                    and not _has_wall(x + 1, y)
                    and not _has_wall(x + 1, y - 1),
                    not _has_wall(x, y + 1)
                    and not _has_wall(x + 1, y)
                    and not _has_wall(x + 1, y + 1),
                    not _has_wall(x, y + 1)
                    and not _has_wall(x - 1, y)
                    and not _has_wall(x - 1, y + 1),
                )
                if any(bevel_mask):
                    bevel_corners[(x, y)] = bevel_mask
                wall_cell = (x, y)
                wall = ReinforcedWall(
                    cell_rect.x,
                    cell_rect.y,
                    cell_rect.width,
                    cell_rect.height,
                    health=OUTER_WALL_HEALTH,
                    palette=palette,
                    bevel_depth=INTERNAL_WALL_BEVEL_DEPTH,
                    bevel_mask=bevel_mask,
                    draw_bottom_side=draw_bottom_side,
                    on_destroy=(lambda _w, cell=wall_cell: remove_wall_cell(cell)),
                )
                wall_group.add(wall)
                all_sprites.add(wall, layer=LAYER_WALLS)
                continue
            if ch == "x":
                pitfall_cells.add((x, y))
                continue
            if ch == "F":
                fire_floor_cells.add((x, y))
                continue
            if ch == "m":
                metal_floor_cells.add((x, y))
                if not cell_has_beam:
                    walkable_cells.append((x, y))
                continue
            if ch == "h":
                spiky_plant_cells.add((x, y))
                if not cell_has_beam:
                    walkable_cells.append((x, y))
                continue
            if ch == "w":
                puddle_cells.add((x, y))
                if not cell_has_beam:
                    walkable_cells.append((x, y))
                continue
            if ch == "E":
                if not cell_has_beam:
                    walkable_cells.append((x, y))
            elif ch == "1":
                beam = None
                if cell_has_beam:
                    beam = SteelBeam(
                        cell_rect.x,
                        cell_rect.y,
                        cell_rect.width,
                        health=STEEL_BEAM_HEALTH,
                        palette=palette,
                        on_destroy=(
                            lambda _b, cell=(x, y): remove_steel_beam_cell(cell)
                        ),
                    )
                draw_bottom_side = not _has_wall(x, y + 1)
                bevel_mask = (
                    not _has_wall(x, y - 1)
                    and not _has_wall(x - 1, y)
                    and not _has_wall(x - 1, y - 1),
                    not _has_wall(x, y - 1)
                    and not _has_wall(x + 1, y)
                    and not _has_wall(x + 1, y - 1),
                    not _has_wall(x, y + 1)
                    and not _has_wall(x + 1, y)
                    and not _has_wall(x + 1, y + 1),
                    not _has_wall(x, y + 1)
                    and not _has_wall(x - 1, y)
                    and not _has_wall(x - 1, y + 1),
                )
                if any(bevel_mask):
                    bevel_corners[(x, y)] = bevel_mask
                wall_cell = (x, y)
                use_rubble = rubble_ratio > 0 and random.random() < rubble_ratio
                if use_rubble:
                    rotation_deg = (
                        RUBBLE_ROTATION_DEG
                        if random.random() < 0.5
                        else -RUBBLE_ROTATION_DEG
                    )
                    wall = RubbleWall(
                        cell_rect.x,
                        cell_rect.y,
                        cell_rect.width,
                        cell_rect.height,
                        health=INTERNAL_WALL_HEALTH,
                        palette=palette,
                        palette_category="inner_wall",
                        bevel_depth=INTERNAL_WALL_BEVEL_DEPTH,
                        rubble_rotation_deg=rotation_deg,
                        on_destroy=(
                            (
                                lambda _w, b=beam, cell=wall_cell: (
                                    remove_wall_cell(cell, allow_walkable=False),
                                    add_beam_to_groups(b, cell=cell),
                                )
                            )
                            if beam
                            else (lambda _w, cell=wall_cell: remove_wall_cell(cell))
                        ),
                    )
                else:
                    wall = Wall(
                        cell_rect.x,
                        cell_rect.y,
                        cell_rect.width,
                        cell_rect.height,
                        health=INTERNAL_WALL_HEALTH,
                        palette=palette,
                        palette_category="inner_wall",
                        bevel_mask=bevel_mask,
                        draw_bottom_side=draw_bottom_side,
                        on_destroy=(
                            (
                                lambda _w, b=beam, cell=wall_cell: (
                                    remove_wall_cell(cell, allow_walkable=False),
                                    add_beam_to_groups(b, cell=cell),
                                )
                            )
                            if beam
                            else (lambda _w, cell=wall_cell: remove_wall_cell(cell))
                        ),
                    )
                wall_group.add(wall)
                all_sprites.add(wall, layer=LAYER_WALLS)
            else:
                if not cell_has_beam:
                    walkable_cells.append((x, y))

            if ch in {"^", "v", "<", ">"}:
                if ch == "^":
                    moving_floor_cells[(x, y)] = MovingFloorDirection.UP
                elif ch == "v":
                    moving_floor_cells[(x, y)] = MovingFloorDirection.DOWN
                elif ch == "<":
                    moving_floor_cells[(x, y)] = MovingFloorDirection.LEFT
                else:
                    moving_floor_cells[(x, y)] = MovingFloorDirection.RIGHT
                if not cell_has_beam and (x, y) not in walkable_cells:
                    walkable_cells.append((x, y))
            if ch == "P":
                player_cells.append((x, y))
            if ch == "C":
                car_cells.append((x, y))
            if ch == "f":
                fuel_cells.append((x, y))
            if ch == "e":
                empty_fuel_can_cells.append((x, y))
            if ch == "l":
                flashlight_cells.append((x, y))
            if ch == "s":
                shoes_cells.append((x, y))

            if cell_has_beam and ch != "1":
                beam = SteelBeam(
                    cell_rect.x,
                    cell_rect.y,
                    cell_rect.width,
                    health=STEEL_BEAM_HEALTH,
                    palette=palette,
                    on_destroy=(lambda _b, cell=(x, y): remove_steel_beam_cell(cell)),
                )
                add_beam_to_groups(beam, cell=(x, y))

    return _WorldBuildResult(
        outer_wall_cells=outer_wall_cells,
        wall_cells=wall_cells,
        steel_beam_cells=steel_beam_cells,
        outside_cells=outside_cells,
        moving_floor_cells=moving_floor_cells,
        walkable_cells=walkable_cells,
        pitfall_cells=pitfall_cells,
        fire_floor_cells=fire_floor_cells,
        metal_floor_cells=metal_floor_cells,
        spiky_plant_cells=spiky_plant_cells,
        puddle_cells=puddle_cells,
        player_cells=player_cells,
        car_cells=car_cells,
        fuel_cells=fuel_cells,
        empty_fuel_can_cells=empty_fuel_can_cells,
        flashlight_cells=flashlight_cells,
        shoes_cells=shoes_cells,
        bevel_corners=bevel_corners,
    )


def generate_level_from_blueprint(
    stage: Stage,
    config: dict[str, Any],
    *,
    seed: int | None,
    ambient_palette_key: str | None,
) -> tuple[
    LevelLayout,
    dict[str, list[tuple[int, int]]],
    pygame.sprite.Group,
    pygame.sprite.LayeredUpdates,
    Blueprint,
]:
    """Build walls/spawn candidates/outside area from a blueprint grid."""
    wall_group = pygame.sprite.Group()
    all_sprites = pygame.sprite.LayeredUpdates()

    steel_conf = config.get("steel_beams", {})
    steel_enabled = steel_conf.get("enabled", False)

    base_moving_floor_cells = _expand_moving_floor_cells(stage)
    fuel_count = 0
    empty_fuel_can_count = 0
    fuel_station_count = 0
    if stage.fuel_mode < FuelMode.START_FULL and not stage.endurance_stage:
        if stage.fuel_mode == FuelMode.REFUEL_CHAIN:
            empty_fuel_can_count = max(1, int(stage.empty_fuel_can_spawn_count))
            fuel_station_count = max(1, int(stage.fuel_station_spawn_count))
        else:
            fuel_count = max(0, int(stage.fuel_spawn_count))
    flashlight_count = max(0, int(stage.flashlight_spawn_count))
    shoes_count = max(0, int(stage.shoes_spawn_count))

    steel_conf = config.get("steel_beams", {})
    try:
        steel_chance = float(steel_conf.get("chance", DEFAULT_STEEL_BEAM_CHANCE))
    except (TypeError, ValueError):
        steel_chance = DEFAULT_STEEL_BEAM_CHANCE

    blueprint_data = _generate_valid_blueprint_with_retries(
        stage=stage,
        seed=seed,
        steel_chance=steel_chance,
        moving_floor_cells=base_moving_floor_cells,
        fuel_count=fuel_count,
        empty_fuel_can_count=empty_fuel_can_count,
        fuel_station_count=fuel_station_count,
        flashlight_count=flashlight_count,
        shoes_count=shoes_count,
    )
    blueprint = blueprint_data.grid
    steel_cells_raw = blueprint_data.steel_cells
    car_reachable_cells = blueprint_data.car_reachable_cells

    steel_cells = (
        {(int(x), int(y)) for x, y in steel_cells_raw} if steel_enabled else set()
    )
    world = _build_world_from_blueprint(
        stage=stage,
        blueprint=blueprint,
        wall_group=wall_group,
        all_sprites=all_sprites,
        steel_enabled=steel_enabled,
        steel_cells=steel_cells,
        ambient_palette_key=ambient_palette_key,
    )

    outside_cells = world.outside_cells
    outer_wall_cells = world.outer_wall_cells
    wall_cells = world.wall_cells
    steel_beam_cells = world.steel_beam_cells
    moving_floor_cells = world.moving_floor_cells
    walkable_cells = world.walkable_cells
    pitfall_cells = world.pitfall_cells
    fire_floor_cells = world.fire_floor_cells
    metal_floor_cells = world.metal_floor_cells
    spiky_plant_cells = world.spiky_plant_cells
    puddle_cells = world.puddle_cells
    player_cells = world.player_cells
    car_cells = world.car_cells
    fuel_cells = world.fuel_cells
    empty_fuel_can_cells = world.empty_fuel_can_cells
    flashlight_cells = world.flashlight_cells
    shoes_cells = world.shoes_cells
    bevel_corners = world.bevel_corners

    interior_min_x = 2
    interior_max_x = stage.grid_cols - 3
    interior_min_y = 2
    interior_max_y = stage.grid_rows - 3
    cell_size = stage.cell_size

    layout = LevelLayout(
        field_rect=pygame.Rect(
            0,
            0,
            stage.grid_cols * cell_size,
            stage.grid_rows * cell_size,
        ),
        grid_cols=stage.grid_cols,
        grid_rows=stage.grid_rows,
        outside_cells=outside_cells,
        walkable_cells=[],
        outer_wall_cells=outer_wall_cells,
        wall_cells=wall_cells,
        steel_beam_cells=steel_beam_cells,
        pitfall_cells=pitfall_cells,
        car_walkable_cells=car_reachable_cells,
        car_spawn_cells=[],
        fall_spawn_cells=set(),
        spiky_plant_cells=spiky_plant_cells,
        fire_floor_cells=fire_floor_cells,
        metal_floor_cells=metal_floor_cells,
        zombie_contaminated_cells=set(),
        puddle_cells=puddle_cells,
        bevel_corners=bevel_corners,
        moving_floor_cells={},
        floor_ruin_cells={},
    )
    (
        walkable_cells,
        item_spawn_cells,
        car_spawn_cells,
        filtered_car_cells,
    ) = _finalize_layout_cells(
        stage=stage,
        layout=layout,
        walkable_cells=walkable_cells,
        pitfall_cells=pitfall_cells,
        fire_floor_cells=fire_floor_cells,
        metal_floor_cells=metal_floor_cells,
        puddle_cells=puddle_cells,
        moving_floor_cells=moving_floor_cells,
        spiky_plant_cells=spiky_plant_cells,
        car_reachable_cells=car_reachable_cells,
        car_cells=car_cells,
        interior_min_x=interior_min_x,
        interior_max_x=interior_max_x,
        interior_min_y=interior_min_y,
        interior_max_y=interior_max_y,
    )
    layout.outer_wall_cells = outer_wall_cells
    layout.wall_cells = wall_cells
    layout.steel_beam_cells = steel_beam_cells
    layout.bevel_corners = bevel_corners

    layout_data = _build_layout_data(
        layout=layout,
        player_cells=player_cells,
        filtered_car_cells=filtered_car_cells,
        fuel_cells=fuel_cells,
        empty_fuel_can_cells=empty_fuel_can_cells,
        flashlight_cells=flashlight_cells,
        shoes_cells=shoes_cells,
        spiky_plant_cells=spiky_plant_cells,
        fire_floor_cells=fire_floor_cells,
        metal_floor_cells=metal_floor_cells,
        puddle_cells=puddle_cells,
        walkable_cells=walkable_cells,
        car_reachable_cells=car_reachable_cells,
        item_spawn_cells=item_spawn_cells,
        car_spawn_cells=car_spawn_cells,
    )

    return (
        layout,
        layout_data,
        wall_group,
        all_sprites,
        blueprint_data,
    )
