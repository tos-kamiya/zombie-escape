import pygame

from zombie_escape.gameplay.spatial_index import SpatialIndex, SpatialKind


def _make_sprite(center: tuple[int, int]) -> pygame.sprite.Sprite:
    spr = pygame.sprite.Sprite()
    spr.rect = pygame.Rect(0, 0, 10, 10)
    spr.rect.center = center
    return spr


def test_query_cells_filters_by_cell_window_and_kind() -> None:
    index = SpatialIndex(cell_size=32)
    zombie = _make_sprite((32, 32))  # (1,1)
    dog = _make_sprite((64, 32))  # (2,1)
    far = _make_sprite((160, 160))  # (5,5)
    index.insert(zombie, SpatialKind.ZOMBIE)
    index.insert(dog, SpatialKind.ZOMBIE_DOG)
    index.insert(far, SpatialKind.ZOMBIE)

    found = index.query_cells(
        min_cell_x=0,
        max_cell_x=2,
        min_cell_y=0,
        max_cell_y=2,
        kinds=SpatialKind.ZOMBIE,
    )
    assert zombie in found
    assert dog not in found
    assert far not in found


def test_query_cells_returns_empty_when_window_invalid() -> None:
    index = SpatialIndex(cell_size=32)
    found = index.query_cells(
        min_cell_x=2,
        max_cell_x=1,
        min_cell_y=0,
        max_cell_y=0,
        kinds=SpatialKind.ALL,
    )
    assert found == []
