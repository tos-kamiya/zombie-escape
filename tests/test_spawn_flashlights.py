import pygame

from zombie_escape.entities import Player
from zombie_escape.gameplay.spawn import place_flashlights


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def test_place_flashlights_uses_blueprint_cells_without_clustering_drop() -> None:
    _init_pygame()
    player = Player(20, 20)
    cells = [(5, 5), (6, 5), (7, 5)]

    flashlights = place_flashlights(
        cells,
        40,
        player,
        cars=[],
        reserved_centers=set(),
        count=3,
    )

    assert len(flashlights) == 3
