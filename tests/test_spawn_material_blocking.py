from types import SimpleNamespace

import pytest

from zombie_escape.gameplay.spawn import (
    setup_player_and_cars,
    spawn_initial_carrier_bots_and_materials,
)
from zombie_escape.level_constants import DEFAULT_CELL_SIZE
from zombie_escape.models import LevelLayout, Stage

pygame = pytest.importorskip("pygame")


def test_setup_player_and_cars_avoids_material_spawn_cells() -> None:
    if not pygame.get_init():
        pygame.init()

    stage = Stage(
        id="material_blocking_spawn",
        name_key="n",
        description_key="d",
        cell_size=DEFAULT_CELL_SIZE,
        grid_cols=10,
        grid_rows=10,
        zombie_normal_ratio=1.0,
        material_spawns=[(2, 2)],
    )
    game_data = SimpleNamespace(
        stage=stage,
        cell_size=DEFAULT_CELL_SIZE,
        layout=SimpleNamespace(field_rect=pygame.Rect(0, 0, 500, 500)),
        groups=SimpleNamespace(all_sprites=pygame.sprite.LayeredUpdates()),
    )
    layout_data = {
        "walkable_cells": [(2, 2), (3, 2)],
        "player_cells": [(2, 2)],
        "car_cells": [(2, 2), (3, 2)],
        "car_spawn_cells": [(2, 2), (3, 2)],
        "spiky_plant_cells": [],
    }

    player, cars = setup_player_and_cars(game_data, layout_data, car_count=1)
    assert cars
    player_cell = (
        int(player.rect.centerx // DEFAULT_CELL_SIZE),
        int(player.rect.centery // DEFAULT_CELL_SIZE),
    )
    car_cell = (
        int(cars[0].rect.centerx // DEFAULT_CELL_SIZE),
        int(cars[0].rect.centery // DEFAULT_CELL_SIZE),
    )
    assert player_cell != (2, 2)
    assert car_cell != (2, 2)


def test_material_spawn_avoids_waiting_car_cells() -> None:
    if not pygame.get_init():
        pygame.init()

    stage = Stage(
        id="material_avoid_car_spawn_cell",
        name_key="n",
        description_key="d",
        cell_size=DEFAULT_CELL_SIZE,
        grid_cols=10,
        grid_rows=10,
        zombie_normal_ratio=1.0,
        material_spawns=[(2, 2)],
    )
    layout = LevelLayout(
        field_rect=pygame.Rect(0, 0, 500, 500),
        grid_cols=10,
        grid_rows=10,
        outside_cells=set(),
        walkable_cells=[],
        outer_wall_cells=set(),
        wall_cells=set(),
        steel_beam_cells=set(),
        pitfall_cells=set(),
        car_walkable_cells=set(),
        car_spawn_cells=[(2, 2)],
        fall_spawn_cells=set(),
        spiky_plant_cells=set(),
    )
    parked = SimpleNamespace(
        rect=pygame.Rect(0, 0, 10, 10),
        alive=lambda: True,
    )
    parked.rect.center = (
        int((2 * DEFAULT_CELL_SIZE) + (DEFAULT_CELL_SIZE // 2)),
        int((2 * DEFAULT_CELL_SIZE) + (DEFAULT_CELL_SIZE // 2)),
    )
    groups = SimpleNamespace(
        all_sprites=pygame.sprite.LayeredUpdates(),
        material_group=pygame.sprite.Group(),
        carrier_bot_group=pygame.sprite.Group(),
        wall_group=pygame.sprite.Group(),
    )
    game_data = SimpleNamespace(
        stage=stage,
        cell_size=DEFAULT_CELL_SIZE,
        layout=layout,
        groups=groups,
        car=None,
        waiting_cars=[parked],
    )

    spawn_initial_carrier_bots_and_materials(game_data)
    assert len(groups.material_group.sprites()) == 0
