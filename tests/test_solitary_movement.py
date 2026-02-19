import pygame

from zombie_escape.entities import Zombie
from zombie_escape.entities.zombie_movement import _zombie_solitary_movement
from zombie_escape.entities_constants import ZombieKind
from zombie_escape.level_constants import (
    DEFAULT_CELL_SIZE,
    DEFAULT_GRID_COLS,
    DEFAULT_GRID_ROWS,
)
from zombie_escape.models import LevelLayout


def _make_layout() -> LevelLayout:
    return LevelLayout(
        field_rect=pygame.Rect(
            0,
            0,
            DEFAULT_GRID_COLS * DEFAULT_CELL_SIZE,
            DEFAULT_GRID_ROWS * DEFAULT_CELL_SIZE,
        ),
        grid_cols=DEFAULT_GRID_COLS,
        grid_rows=DEFAULT_GRID_ROWS,
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
        puddle_cells=set(),
        bevel_corners={},
        moving_floor_cells={},
    )


def test_solitary_keeps_distance_from_player_when_adjacent() -> None:
    solitary = Zombie(100, 100, kind=ZombieKind.SOLITARY)
    layout = _make_layout()

    move_x, move_y = _zombie_solitary_movement(
        solitary,
        DEFAULT_CELL_SIZE,
        layout,
        (100 + DEFAULT_CELL_SIZE, 100),
        [],
        [],
        now_ms=1,
    )

    assert move_x < 0
    assert move_y == 0
