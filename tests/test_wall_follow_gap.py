import math

import pygame

from zombie_escape.entities import Wall, Zombie, zombie_wall_follow_movement
from zombie_escape.level_constants import TILE_SIZE


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def test_wall_follow_turns_away_when_too_close() -> None:
    _init_pygame()
    zombie = Zombie(100, 100, wall_follower=True)
    zombie.wall_follow_side = 1.0
    zombie.wall_follow_angle = 0.0
    wall = Wall(105, 105, 8, 8)

    before = zombie.wall_follow_angle
    zombie_wall_follow_movement(
        zombie,
        (9999, 9999),
        [wall],
        [],
        cell_size=TILE_SIZE,
        outer_wall_cells=set(),
    )
    delta = (zombie.wall_follow_angle - before + math.pi) % (2 * math.pi) - math.pi

    assert delta < 0
