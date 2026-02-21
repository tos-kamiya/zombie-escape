import pytest

from zombie_escape.render_assets import (
    paint_wall_damage_overlay,
    resolve_wall_colors,
)

pygame = pytest.importorskip("pygame")


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def test_resolve_wall_colors_gets_significantly_darker_with_damage() -> None:
    healthy_fill, healthy_border = resolve_wall_colors(
        health_ratio=1.0,
        palette_category="inner_wall",
        palette=None,
    )
    damaged_fill, damaged_border = resolve_wall_colors(
        health_ratio=0.0,
        palette_category="inner_wall",
        palette=None,
    )
    assert sum(damaged_fill) < sum(healthy_fill)
    assert sum(damaged_border) < sum(healthy_border)


def test_wall_damage_overlay_is_deterministic_for_same_seed() -> None:
    _init_pygame()
    base = (120, 110, 100, 255)
    left = pygame.Surface((48, 48), pygame.SRCALPHA)
    right = pygame.Surface((48, 48), pygame.SRCALPHA)
    left.fill(base)
    right.fill(base)

    paint_wall_damage_overlay(left, health_ratio=0.35, seed=1234)
    paint_wall_damage_overlay(right, health_ratio=0.35, seed=1234)

    assert pygame.image.tobytes(left, "RGBA") == pygame.image.tobytes(right, "RGBA")
