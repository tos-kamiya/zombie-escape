from __future__ import annotations

import random
from typing import Any

import pygame

from ..colors import get_environment_palette
from ..entities import RubbleWall, SteelBeam, Wall
from ..entities_constants import (
    INTERNAL_WALL_BEVEL_DEPTH,
    INTERNAL_WALL_HEALTH,
    STEEL_BEAM_HEALTH,
)
from ..render_assets import RUBBLE_ROTATION_DEG
from .constants import OUTER_WALL_HEALTH
from ..level_blueprints import MapGenerationError, choose_blueprint
from ..models import GameData
from ..rng import get_rng

__all__ = ["generate_level_from_blueprint", "MapGenerationError"]

RNG = get_rng()



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


def generate_level_from_blueprint(
    game_data: GameData, config: dict[str, Any]
) -> dict[str, list[pygame.Rect]]:
    """Build walls/spawn candidates/outside area from a blueprint grid."""
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    stage = game_data.stage

    steel_conf = config.get("steel_beams", {})
    steel_enabled = steel_conf.get("enabled", False)

    blueprint_data = choose_blueprint(
        config,
        cols=stage.grid_cols,
        rows=stage.grid_rows,
        wall_algo=stage.wall_algorithm,
        pitfall_density=getattr(stage, "pitfall_density", 0.0),
        pitfall_zones=getattr(stage, "pitfall_zones", []),
        base_seed=game_data.state.seed,
    )
    if isinstance(blueprint_data, dict):
        blueprint = blueprint_data.get("grid", [])
        steel_cells_raw = blueprint_data.get("steel_cells", set())
        car_reachable_cells = blueprint_data.get("car_reachable_cells", set())
    else:
        blueprint = blueprint_data
        steel_cells_raw = set()
        car_reachable_cells = set()

    steel_cells = (
        {(int(x), int(y)) for x, y in steel_cells_raw} if steel_enabled else set()
    )
    game_data.layout.car_walkable_cells = car_reachable_cells
    cell_size = game_data.cell_size
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
        if ch in {"B", "1"}
    }

    def _has_wall(nx: int, ny: int) -> bool:
        if nx < 0 or ny < 0 or nx >= stage.grid_cols or ny >= stage.grid_rows:
            return True
        return (nx, ny) in wall_cells

    outside_cells: set[tuple[int, int]] = set()
    walkable_cells: list[tuple[int, int]] = []
    pitfall_cells: set[tuple[int, int]] = set()
    player_cells: list[tuple[int, int]] = []
    car_cells: list[tuple[int, int]] = []
    zombie_cells: list[tuple[int, int]] = []
    fuel_cells: list[tuple[int, int]] = []
    flashlight_cells: list[tuple[int, int]] = []
    shoes_cells: list[tuple[int, int]] = []
    interior_min_x = 2
    interior_max_x = stage.grid_cols - 3
    interior_min_y = 2
    interior_max_y = stage.grid_rows - 3
    bevel_corners: dict[tuple[int, int], tuple[bool, bool, bool, bool]] = {}
    palette = get_environment_palette(game_data.state.ambient_palette_key)
    rubble_ratio = max(0.0, min(1.0, getattr(stage, "wall_rubble_ratio", 0.0)))

    def add_beam_to_groups(beam: SteelBeam) -> None:
        if beam._added_to_groups:
            return
        wall_group.add(beam)
        all_sprites.add(beam, layer=0)
        beam._added_to_groups = True

    def remove_wall_cell(cell: tuple[int, int]) -> None:
        wall_cells.discard(cell)
        outer_wall_cells.discard(cell)

    for y, row in enumerate(blueprint):
        if len(row) != stage.grid_cols:
            raise ValueError(
                "Blueprint width mismatch at row "
                f"{y}: {len(row)} != {stage.grid_cols}"
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
                all_sprites.add(wall, layer=0)
                continue
            if ch == "x":
                pitfall_cells.add((x, y))
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
                                    remove_wall_cell(cell),
                                    add_beam_to_groups(b),
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
                                    remove_wall_cell(cell),
                                    add_beam_to_groups(b),
                                )
                            )
                            if beam
                            else (lambda _w, cell=wall_cell: remove_wall_cell(cell))
                        ),
                    )
                wall_group.add(wall)
                all_sprites.add(wall, layer=0)
            else:
                if not cell_has_beam:
                    walkable_cells.append((x, y))

            if ch == "P":
                player_cells.append((x, y))
            if ch == "C":
                car_cells.append((x, y))
            if ch == "Z":
                zombie_cells.append((x, y))
            if ch == "f":
                fuel_cells.append((x, y))
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
                )
                add_beam_to_groups(beam)

    game_data.layout.field_rect = pygame.Rect(
        0,
        0,
        game_data.level_width,
        game_data.level_height,
    )
    game_data.layout.outside_cells = outside_cells
    game_data.layout.walkable_cells = walkable_cells
    game_data.layout.outer_wall_cells = outer_wall_cells
    game_data.layout.wall_cells = wall_cells
    game_data.layout.pitfall_cells = pitfall_cells
    fall_spawn_cells = _expand_zone_cells(
        stage.fall_spawn_zones,
        grid_cols=stage.grid_cols,
        grid_rows=stage.grid_rows,
    )
    floor_ratio = max(0.0, min(1.0, stage.fall_spawn_floor_ratio))
    if floor_ratio > 0.0 and interior_min_x <= interior_max_x:
        for y in range(interior_min_y, interior_max_y + 1):
            for x in range(interior_min_x, interior_max_x + 1):
                if RNG.random() < floor_ratio:
                    fall_spawn_cells.add((x, y))
        if not fall_spawn_cells:
            fall_spawn_cells.add(
                (
                    RNG.randint(interior_min_x, interior_max_x),
                    RNG.randint(interior_min_y, interior_max_y),
                )
            )
    game_data.layout.fall_spawn_cells = fall_spawn_cells
    game_data.layout.bevel_corners = bevel_corners

    return {
        "player_cells": player_cells,
        "car_cells": car_cells,
        "zombie_cells": zombie_cells,
        "fuel_cells": fuel_cells,
        "flashlight_cells": flashlight_cells,
        "shoes_cells": shoes_cells,
        "walkable_cells": walkable_cells,
        "car_walkable_cells": list(car_reachable_cells),
    }
