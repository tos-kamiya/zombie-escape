import pygame

from zombie_escape.entities import Zombie
from zombie_escape.entities.zombie_movement import _zombie_loner_movement
from zombie_escape.entities_constants import ZombieKind
from zombie_escape.level_constants import DEFAULT_CELL_SIZE, DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS
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
        pitfall_cells=set(),
        car_walkable_cells=set(),
        car_spawn_cells=[],
        fall_spawn_cells=set(),
        houseplant_cells=set(),
        puddle_cells=set(),
        bevel_corners={},
        moving_floor_cells={},
    )


def test_loner_chases_target_when_within_short_range() -> None:
    loner = Zombie(100, 100, kind=ZombieKind.LONER)
    layout = _make_layout()

    move_x, move_y = _zombie_loner_movement(
        loner,
        [],
        DEFAULT_CELL_SIZE,
        layout,
        (110, 100),
        [],
        [],
        now_ms=1,
    )

    assert move_x > 0
    assert move_y == 0
