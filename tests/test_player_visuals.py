import pytest

from zombie_escape.entities.player import Player
from zombie_escape.render_assets import build_zombie_directional_surfaces

pygame = pytest.importorskip("pygame")


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def test_player_zombified_visual_uses_handless_zombie_surfaces() -> None:
    _init_pygame()
    player = Player(100, 120)
    original_images = player.directional_images
    original_center = player.rect.center

    player.set_zombified_visual()

    expected = build_zombie_directional_surfaces(player.radius, draw_hands=False)
    assert player.is_zombified_visual is True
    assert player.directional_images is expected
    assert player.directional_images is not original_images
    assert player.rect.center == original_center
