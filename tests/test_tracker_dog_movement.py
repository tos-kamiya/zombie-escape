import math

import pygame

from zombie_escape.entities import Zombie
from zombie_escape.entities.zombie_dog import (
    ZombieDog,
    ZombieDogMode,
    _zombie_dog_default_movement,
    _zombie_dog_tracker_movement,
)
from zombie_escape.entities_constants import ZOMBIE_DOG_TRACKER_FOLLOW_SPEED_MULTIPLIER
from zombie_escape.entities_constants import ZombieKind
from zombie_escape.level_constants import (
    DEFAULT_CELL_SIZE,
    DEFAULT_GRID_COLS,
    DEFAULT_GRID_ROWS,
)
from zombie_escape.models import Footprint, LevelLayout
from zombie_escape.render_assets import angle_bin_from_vector
from zombie_escape.render_constants import ZOMBIE_NOSE_COLOR


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


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
        fire_floor_cells=set(),
        puddle_cells=set(),
        bevel_corners={},
        moving_floor_cells={},
    )


def test_tracker_dog_follows_footprints_out_of_sight() -> None:
    _init_pygame()
    layout = _make_layout()
    dog = ZombieDog(50, 50, variant="tracker")
    dog.tracker_state.scan_interval_ms = 0
    dog.tracker_state.last_scan_time = -999999
    footprints = [Footprint(pos=(90, 50), time=1000)]

    move_x, move_y = _zombie_dog_tracker_movement(
        dog,
        DEFAULT_CELL_SIZE,
        layout,
        (9999.0, 9999.0),
        [],
        footprints,
        now_ms=0,
    )

    assert dog.mode != ZombieDogMode.CHASE
    assert dog.tracker_target_pos == (90, 50)
    assert move_x > 0
    assert abs(move_y) < 1e-6
    assert math.isclose(
        move_x,
        dog.speed_patrol * ZOMBIE_DOG_TRACKER_FOLLOW_SPEED_MULTIPLIER,
        rel_tol=1e-6,
        abs_tol=1e-6,
    )


def test_tracker_dog_charges_when_player_in_sight() -> None:
    _init_pygame()
    layout = _make_layout()
    dog = ZombieDog(50, 50, variant="tracker")
    dog.tracker_state.scan_interval_ms = 0
    dog.tracker_state.last_scan_time = -999999

    move_x, move_y = _zombie_dog_tracker_movement(
        dog,
        DEFAULT_CELL_SIZE,
        layout,
        (100.0, 100.0),
        [],
        [],
        now_ms=0,
    )

    assert dog.mode == ZombieDogMode.CHARGE
    assert (move_x, move_y) == (0.0, 0.0)


def test_tracker_dog_disables_pack_chase_mode() -> None:
    _init_pygame()
    layout = _make_layout()
    dog = ZombieDog(50, 50, variant="tracker")
    dog.tracker_state.scan_interval_ms = 0
    dog.tracker_state.last_scan_time = -999999
    nearby_zombie = Zombie(52, 50, kind=ZombieKind.NORMAL)

    _zombie_dog_tracker_movement(
        dog,
        DEFAULT_CELL_SIZE,
        layout,
        (9999.0, 9999.0),
        [nearby_zombie],
        [],
        now_ms=0,
    )

    assert dog.mode != ZombieDogMode.CHASE


def test_normal_dog_charge_has_two_frame_windup_and_faces_player() -> None:
    _init_pygame()
    layout = _make_layout()
    dog = ZombieDog(50, 50, variant="normal")
    player = (120.0, 120.0)

    move_1 = _zombie_dog_default_movement(
        dog,
        DEFAULT_CELL_SIZE,
        layout,
        player,
        [],
        [],
        now_ms=0,
    )
    assert dog.mode == ZombieDogMode.CHARGE
    assert move_1 == (0.0, 0.0)
    expected_bin = angle_bin_from_vector(player[0] - dog.x, player[1] - dog.y)
    assert expected_bin is not None
    assert dog.facing_bin == expected_bin

    move_2 = _zombie_dog_default_movement(
        dog,
        DEFAULT_CELL_SIZE,
        layout,
        player,
        [],
        [],
        now_ms=1,
    )
    assert move_2 == (0.0, 0.0)

    move_3 = _zombie_dog_default_movement(
        dog,
        DEFAULT_CELL_SIZE,
        layout,
        player,
        [],
        [],
        now_ms=2,
    )
    assert math.hypot(move_3[0], move_3[1]) > 0.0


def _count_rgb_pixels(
    surface: pygame.Surface, rgb: tuple[int, int, int]
) -> int:
    width, height = surface.get_size()
    count = 0
    for y in range(height):
        for x in range(width):
            if surface.get_at((x, y))[:3] == rgb:
                count += 1
    return count


def test_tracker_dog_draws_nose_marker_overlay() -> None:
    _init_pygame()
    tracker = ZombieDog(50, 50, variant="tracker")
    normal = ZombieDog(50, 50, variant="normal")

    tracker._set_facing_bin(0)
    normal._set_facing_bin(0)
    tracker.refresh_image()
    normal.refresh_image()

    tracker_nose_pixels = _count_rgb_pixels(tracker.image, ZOMBIE_NOSE_COLOR)
    normal_nose_pixels = _count_rgb_pixels(normal.image, ZOMBIE_NOSE_COLOR)
    assert tracker_nose_pixels > normal_nose_pixels
