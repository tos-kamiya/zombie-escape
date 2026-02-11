import math

import pygame

from src.zombie_escape.level_constants import DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS
from zombie_escape.entities import Wall, Zombie
from zombie_escape.entities_constants import ZombieKind
from zombie_escape.entities.movement import _zombie_wall_hug_movement
from zombie_escape.level_constants import DEFAULT_CELL_SIZE
from zombie_escape.models import LevelLayout


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def test_wall_hug_turns_away_when_too_close() -> None:
    _init_pygame()
    zombie = Zombie(100, 100, kind=ZombieKind.WALL_HUGGER)
    zombie.wall_hug_side = 1.0
    zombie.wall_hug_angle = 0.0
    wall = Wall(105, 105, 8, 8)
    layout = LevelLayout(
        field_rect=pygame.Rect(
            0,
            0,
            DEFAULT_GRID_COLS * DEFAULT_CELL_SIZE,
            DEFAULT_GRID_ROWS * DEFAULT_CELL_SIZE,
        ),
        grid_cols=DEFAULT_GRID_COLS,
        grid_rows=DEFAULT_GRID_ROWS,
        outside_cells=set(),
        walkable_cells=[],
        outer_wall_cells=set(),
        wall_cells=set(),
        pitfall_cells=set(),
        car_walkable_cells=set(),
        car_spawn_cells=[],
        fall_spawn_cells=set(),
        bevel_corners={},
        moving_floor_cells={},
    )

    before = zombie.wall_hug_angle
    _zombie_wall_hug_movement(
        zombie,
        [wall],
        DEFAULT_CELL_SIZE,
        layout,
        (9999, 9999),
        [],
        [],
        now_ms=0,
    )
    delta = (zombie.wall_hug_angle - before + math.pi) % (2 * math.pi) - math.pi

    assert delta < 0
