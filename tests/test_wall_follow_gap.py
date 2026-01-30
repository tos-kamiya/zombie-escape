import math

import pygame

from src.zombie_escape.level_constants import DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS
from zombie_escape.entities import Wall, Zombie, _zombie_wall_hug_movement
from zombie_escape.level_constants import DEFAULT_TILE_SIZE


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def test_wall_hug_turns_away_when_too_close() -> None:
    _init_pygame()
    zombie = Zombie(100, 100, wall_hugging=True)
    zombie.wall_hug_side = 1.0
    zombie.wall_hug_angle = 0.0
    wall = Wall(105, 105, 8, 8)

    before = zombie.wall_hug_angle
    _zombie_wall_hug_movement(
        zombie,
        (9999, 9999),
        [wall],
        [],
        cell_size=DEFAULT_TILE_SIZE,
        grid_cols=DEFAULT_GRID_COLS,
        grid_rows=DEFAULT_GRID_ROWS,
        outer_wall_cells=set(),
    )
    delta = (zombie.wall_hug_angle - before + math.pi) % (2 * math.pi) - math.pi

    assert delta < 0
