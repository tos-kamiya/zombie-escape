import pytest

from zombie_escape.entities.car import Car
from zombie_escape.entities.player import Player
from zombie_escape.entities.survivor import Survivor
from zombie_escape.level_constants import DEFAULT_CELL_SIZE
from zombie_escape.models import LevelLayout

pygame = pytest.importorskip("pygame")


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def _make_layout(*, width: int, height: int, material_cells: set[tuple[int, int]]) -> LevelLayout:
    return LevelLayout(
        field_rect=pygame.Rect(0, 0, width, height),
        grid_cols=max(1, width // DEFAULT_CELL_SIZE),
        grid_rows=max(1, height // DEFAULT_CELL_SIZE),
        outside_cells=set(),
        walkable_cells=[],
        outer_wall_cells=set(),
        wall_cells=set(),
        steel_beam_cells=set(),
        pitfall_cells=set(),
        car_walkable_cells=set(),
        car_spawn_cells=[],
        fall_spawn_cells=set(),
        spiky_plant_cells=set(),
        material_cells=set(material_cells),
    )


def test_player_treats_material_as_blocking_cell() -> None:
    _init_pygame()
    layout = _make_layout(width=200, height=100, material_cells={(1, 0)})
    player = Player(25, 25)
    walls = pygame.sprite.Group()

    player.move(
        40.0,
        0.0,
        walls,
        patrol_bot_group=None,
        wall_index=None,
        cell_size=DEFAULT_CELL_SIZE,
        layout=layout,
        now_ms=0,
    )

    assert player.rect.center == (25, 25)
    assert getattr(player, "pending_pitfall_fall", False) is False


def test_survivor_treats_material_as_blocking_cell() -> None:
    _init_pygame()
    layout = _make_layout(width=200, height=100, material_cells={(1, 0)})
    survivor = Survivor(49, 25)
    walls = pygame.sprite.Group()

    for now_ms in range(0, 300, 16):
        survivor.update_behavior(
            player_pos=(170, 25),
            walls=walls,
            patrol_bot_group=None,
            wall_index=None,
            cell_size=DEFAULT_CELL_SIZE,
            layout=layout,
            now_ms=now_ms,
        )

    assert int(survivor.x // DEFAULT_CELL_SIZE) == 0
    assert getattr(survivor, "pending_pitfall_fall", False) is False


def test_car_treats_material_as_blocking_cell() -> None:
    _init_pygame()
    car = Car(25, 25)

    car.move(
        40.0,
        0.0,
        [],
        walls_nearby=True,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        blocked_cells={(1, 0)},
    )

    assert car.rect.center == (25, 25)
    assert car.pending_pitfall_fall is False
