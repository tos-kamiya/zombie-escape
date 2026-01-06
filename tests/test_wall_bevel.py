import pygame

from zombie_escape.entities import _build_beveled_polygon, rect_polygon_collision


def test_beveled_polygon_top_left_cut() -> None:
    polygon = _build_beveled_polygon(10, 10, 3, (True, False, False, False))
    assert polygon[0] == (3, 0)
    assert polygon[-1] == (0, 3)


def test_rect_collision_respects_bevel() -> None:
    polygon = _build_beveled_polygon(10, 10, 3, (True, False, False, False))
    cut_rect = pygame.Rect(0, 0, 1, 1)
    solid_rect = pygame.Rect(4, 4, 2, 2)
    assert not rect_polygon_collision(cut_rect, polygon)
    assert rect_polygon_collision(solid_rect, polygon)
