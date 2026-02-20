import math

import pygame

from zombie_escape.entities import Zombie
from zombie_escape.entities_constants import ZombieKind, ZOMBIE_TRACKER_LOST_TIMEOUT_MS
from zombie_escape.entities.movement import _zombie_update_tracker_target
from zombie_escape.entities.zombie_movement import _zombie_tracker_movement
from zombie_escape.level_constants import (
    DEFAULT_CELL_SIZE,
    DEFAULT_GRID_COLS,
    DEFAULT_GRID_ROWS,
)
from zombie_escape.models import Footprint, LevelLayout


def _make_footprint(pos: tuple[float, float], time_ms: int) -> Footprint:
    return Footprint(pos=pos, time=time_ms)


def _force_scan(zombie: Zombie) -> None:
    zombie.tracker_scan_interval_ms = 0
    zombie.tracker_last_scan_time = -999999


def _make_layout(*, wall_cells: set[tuple[int, int]]) -> LevelLayout:
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
        wall_cells=wall_cells,
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


def test_tracker_picks_latest_visible_footprint() -> None:
    zombie = Zombie(10, 10, kind=ZombieKind.TRACKER)
    _force_scan(zombie)
    layout = _make_layout(wall_cells=set())
    footprints = [
        _make_footprint((30, 10), 1000),
        _make_footprint((40, 10), 2000),
    ]
    _zombie_update_tracker_target(
        zombie,
        footprints,
        layout,
        cell_size=DEFAULT_CELL_SIZE,
        now_ms=0,
    )
    assert zombie.tracker_target_pos == (40, 10)


def test_tracker_skips_blocked_latest_footprint() -> None:
    zombie = Zombie(10, 10, kind=ZombieKind.TRACKER)
    _force_scan(zombie)
    layout = _make_layout(wall_cells={(1, 0)})
    footprints = [
        _make_footprint((50, 10), 3000),
        _make_footprint((10, 50), 2000),
        _make_footprint((30, 10), 1000),
    ]
    _zombie_update_tracker_target(
        zombie,
        footprints,
        layout,
        cell_size=DEFAULT_CELL_SIZE,
        now_ms=0,
    )
    assert zombie.tracker_target_pos == (10, 50)


def test_tracker_limits_to_top_k_candidates() -> None:
    zombie = Zombie(10, 10, kind=ZombieKind.TRACKER)
    _force_scan(zombie)
    layout = _make_layout(wall_cells={(1, 0), (1, 1)})
    footprints = [
        _make_footprint((50, 10), 4000),
        _make_footprint((60, 15), 3000),
        _make_footprint((70, 5), 2000),
        _make_footprint((10, 40), 1000),
    ]
    _zombie_update_tracker_target(
        zombie,
        footprints,
        layout,
        cell_size=DEFAULT_CELL_SIZE,
        now_ms=0,
    )
    assert zombie.tracker_target_pos is None


def test_tracker_marks_trail_lost_after_timeout_without_newer_footprint() -> None:
    zombie = Zombie(10, 10, kind=ZombieKind.TRACKER)
    _force_scan(zombie)
    layout = _make_layout(wall_cells=set())
    zombie.tracker_target_pos = (40, 10)
    zombie.tracker_target_time = 2000
    zombie.tracker_last_progress_ms = 0
    footprints = [
        _make_footprint((30, 10), 1000),
        _make_footprint((40, 10), 2000),
    ]

    _zombie_update_tracker_target(
        zombie,
        footprints,
        layout,
        cell_size=DEFAULT_CELL_SIZE,
        now_ms=ZOMBIE_TRACKER_LOST_TIMEOUT_MS - 1,
    )
    assert zombie.tracker_target_time == 2000

    _zombie_update_tracker_target(
        zombie,
        footprints,
        layout,
        cell_size=DEFAULT_CELL_SIZE,
        now_ms=ZOMBIE_TRACKER_LOST_TIMEOUT_MS,
    )
    assert zombie.tracker_target_pos is None
    assert zombie.tracker_target_time is None
    assert zombie.tracker_ignore_before_or_at_time == 2000


def test_tracker_reacquires_only_newer_than_lost_boundary() -> None:
    zombie = Zombie(10, 10, kind=ZombieKind.TRACKER)
    _force_scan(zombie)
    layout = _make_layout(wall_cells=set())
    zombie.tracker_ignore_before_or_at_time = 2000
    footprints = [
        _make_footprint((30, 10), 1000),
        _make_footprint((40, 10), 2000),
        _make_footprint((50, 10), 2500),
    ]
    _zombie_update_tracker_target(
        zombie,
        footprints,
        layout,
        cell_size=DEFAULT_CELL_SIZE,
        now_ms=0,
    )
    assert zombie.tracker_target_time == 2500
    assert zombie.tracker_target_pos == (50, 10)


def test_tracker_loss_sets_wander_heading_toward_near_player() -> None:
    zombie = Zombie(110, 110, kind=ZombieKind.TRACKER)
    zombie.tracker_scan_interval_ms = 0
    zombie.tracker_last_scan_time = -999999
    layout = _make_layout(wall_cells=set())
    zombie.tracker_target_pos = (140, 110)
    zombie.tracker_target_time = 2000
    zombie.tracker_last_progress_ms = 0
    footprints = [
        _make_footprint((120, 110), 1000),
        _make_footprint((140, 110), 2000),
    ]
    near_player = (150.0, 110.0)

    move_x, move_y = _zombie_tracker_movement(
        zombie,
        DEFAULT_CELL_SIZE,
        layout,
        near_player,
        [],
        footprints,
        now_ms=ZOMBIE_TRACKER_LOST_TIMEOUT_MS,
    )

    assert zombie.tracker_target_time is None
    assert move_x > 0
    expected = math.atan2(near_player[1] - zombie.y, near_player[0] - zombie.x)
    actual = math.atan2(move_y, move_x)
    assert abs(actual - expected) < 1e-6


def test_tracker_force_wander_sets_initial_wander_heading_toward_near_player() -> None:
    zombie = Zombie(110, 110, kind=ZombieKind.TRACKER)
    zombie.tracker_force_wander = True
    layout = _make_layout(wall_cells=set())
    near_player = (150.0, 110.0)

    move_x, move_y = _zombie_tracker_movement(
        zombie,
        DEFAULT_CELL_SIZE,
        layout,
        near_player,
        [],
        [],
        now_ms=0,
    )

    assert move_x > 0
    expected = math.atan2(near_player[1] - zombie.y, near_player[0] - zombie.x)
    actual = math.atan2(move_y, move_x)
    assert abs(actual - expected) < 1e-6
