import pygame

from zombie_escape.entities.movement import (
    _circle_polygon_collision,
    _rect_polygon_collision,
)
from zombie_escape.entities.walls import _build_beveled_polygon


def test_beveled_polygon_top_left_cut() -> None:
    polygon = _build_beveled_polygon(10, 10, 3, (True, False, False, False))
    assert polygon[0] == (3, 0)
    assert (0, 3) in polygon
    assert len(polygon) > 4


def test_rect_collision_respects_bevel() -> None:
    polygon = _build_beveled_polygon(10, 10, 3, (True, False, False, False))
    solid_rect = pygame.Rect(4, 4, 2, 2)
    assert not _circle_polygon_collision((0, 0), 0, polygon)
    assert _rect_polygon_collision(solid_rect, polygon)
