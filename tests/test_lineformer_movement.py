import pygame

from zombie_escape.entities import Zombie
from zombie_escape.entities_constants import (
    ZombieKind,
    ZOMBIE_LINEFORMER_TARGET_LOST_MS,
)
from zombie_escape.entities.zombie_movement import _zombie_lineformer_movement
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


def test_lineformer_joins_non_lineformer_head() -> None:
    leader = Zombie(120, 120, kind=ZombieKind.NORMAL)
    follower = Zombie(130, 120, kind=ZombieKind.LINEFORMER)
    group = pygame.sprite.Group()
    group.add(leader, follower)
    assert group.has(leader, follower)
    layout = _make_layout()

    _zombie_lineformer_movement(
        follower,
        [],
        DEFAULT_CELL_SIZE,
        layout,
        (0, 0),
        [leader],
        [],
        now_ms=0,
    )

    assert follower.lineformer_follow_target_id == leader.lineformer_id
    assert follower.lineformer_head_id == leader.lineformer_id
    assert follower.lineformer_rank == 1


def test_lineformer_leaves_when_target_chain_breaks() -> None:
    leader = Zombie(120, 120, kind=ZombieKind.NORMAL)
    middle = Zombie(130, 120, kind=ZombieKind.LINEFORMER)
    middle.lineformer_head_id = leader.lineformer_id
    middle.lineformer_follow_target_id = None

    follower = Zombie(140, 120, kind=ZombieKind.LINEFORMER)
    follower.lineformer_head_id = leader.lineformer_id
    follower.lineformer_follow_target_id = middle.lineformer_id
    follower.lineformer_last_target_seen_ms = 0
    group = pygame.sprite.Group()
    group.add(leader, middle, follower)
    assert group.has(leader, middle, follower)
    layout = _make_layout()

    _zombie_lineformer_movement(
        follower,
        [],
        DEFAULT_CELL_SIZE,
        layout,
        (0, 0),
        [leader, middle],
        [],
        now_ms=1,
    )

    assert follower.lineformer_follow_target_id is None
    assert follower.lineformer_head_id is None


def test_lineformer_leaves_after_target_missing_timeout() -> None:
    follower = Zombie(140, 120, kind=ZombieKind.LINEFORMER)
    follower.lineformer_head_id = 1234
    follower.lineformer_follow_target_id = 5678
    follower.lineformer_last_target_seen_ms = 0
    group = pygame.sprite.Group()
    group.add(follower)
    assert group.has(follower)
    layout = _make_layout()

    _zombie_lineformer_movement(
        follower,
        [],
        DEFAULT_CELL_SIZE,
        layout,
        (0, 0),
        [],
        [],
        now_ms=ZOMBIE_LINEFORMER_TARGET_LOST_MS + 1,
    )

    assert follower.lineformer_follow_target_id is None
    assert follower.lineformer_head_id is None


def test_lineformer_leaves_when_duplicate_target_exists() -> None:
    leader = Zombie(120, 120, kind=ZombieKind.NORMAL)
    follower_a = Zombie(130, 120, kind=ZombieKind.LINEFORMER)
    follower_b = Zombie(140, 120, kind=ZombieKind.LINEFORMER)
    follower_a.lineformer_head_id = leader.lineformer_id
    follower_a.lineformer_follow_target_id = leader.lineformer_id
    follower_a.lineformer_last_target_seen_ms = 0
    follower_b.lineformer_head_id = leader.lineformer_id
    follower_b.lineformer_follow_target_id = leader.lineformer_id
    follower_b.lineformer_last_target_seen_ms = 0
    group = pygame.sprite.Group()
    group.add(leader, follower_a, follower_b)
    assert group.has(leader, follower_a, follower_b)
    layout = _make_layout()

    _zombie_lineformer_movement(
        follower_b,
        [],
        DEFAULT_CELL_SIZE,
        layout,
        (0, 0),
        [leader, follower_a],
        [],
        now_ms=1,
    )

    assert follower_b.lineformer_follow_target_id is None
    assert follower_b.lineformer_head_id is None


def test_lineformer_does_not_follow_human_outside_search_radius() -> None:
    follower = Zombie(100, 100, kind=ZombieKind.LINEFORMER)
    group = pygame.sprite.Group()
    group.add(follower)
    assert group.has(follower)
    layout = _make_layout()

    _zombie_lineformer_movement(
        follower,
        [],
        DEFAULT_CELL_SIZE,
        layout,
        (400, 400),
        [],
        [],
        now_ms=1,
    )

    assert follower.lineformer_target_pos is None
