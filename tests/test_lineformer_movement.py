import pygame

from zombie_escape.entities import Zombie
from zombie_escape.entities_constants import (
    ZombieKind,
    ZOMBIE_LINEFORMER_SPEED_MULTIPLIER,
)
from zombie_escape.entities.zombie_movement import (
    _zombie_lineformer_train_head_movement,
)
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
        bevel_corners={},
        moving_floor_cells={},
    )


def test_non_lineformer_ignores_lineformer_for_repulsion() -> None:
    normal = Zombie(100, 100, kind=ZombieKind.NORMAL)
    lineformer = Zombie(101, 100, kind=ZombieKind.LINEFORMER)

    move_x, move_y = normal._avoid_other_zombies(1.0, 0.0, [lineformer])

    assert move_x == 1.0
    assert move_y == 0.0


def test_lineformer_default_strategy_is_train_head_movement() -> None:
    lineformer = Zombie(100, 100, kind=ZombieKind.LINEFORMER)
    layout = _make_layout()

    lineformer.lineformer_target_pos = (200, 100)
    move_x, move_y = lineformer.movement_strategy(
        lineformer,
        [],
        DEFAULT_CELL_SIZE,
        layout,
        (0, 0),
        [],
        [],
        now_ms=1,
    )

    assert move_x > 0
    assert move_y == 0


def test_lineformer_train_head_boosts_movement_only_while_tracking() -> None:
    head = Zombie(100, 100, kind=ZombieKind.LINEFORMER)
    layout = _make_layout()

    head.lineformer_target_pos = None
    wander_x, wander_y = _zombie_lineformer_train_head_movement(
        head,
        [],
        DEFAULT_CELL_SIZE,
        layout,
        (0, 0),
        [],
        [],
        now_ms=1,
    )

    head.lineformer_target_pos = (200, 100)
    chase_x, chase_y = _zombie_lineformer_train_head_movement(
        head,
        [],
        DEFAULT_CELL_SIZE,
        layout,
        (0, 0),
        [],
        [],
        now_ms=2,
    )

    assert chase_x > 0
    assert chase_y == 0
    assert abs(chase_x) == head.speed * ZOMBIE_LINEFORMER_SPEED_MULTIPLIER
    assert abs(wander_x) <= head.speed
    assert abs(wander_y) <= head.speed
