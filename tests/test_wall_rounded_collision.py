import pygame

from zombie_escape.entities import Wall, _build_beveled_polygon


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def test_build_beveled_polygon_rectangle() -> None:
    points = _build_beveled_polygon(20, 20, 5, (False, False, False, False))
    assert points == [(0, 0), (20, 0), (20, 20), (0, 20)]


def test_rounded_wall_corner_collision() -> None:
    _init_pygame()
    wall = Wall(
        0,
        0,
        20,
        20,
        bevel_depth=10,
        bevel_mask=(True, True, True, True),
    )
    assert wall._collides_circle((0, 0), 0)
    assert wall._collides_circle((5, 5), 0)
