import pygame

from zombie_escape.entities import Zombie
from zombie_escape.entities.zombie_dog import (
    ZombieDog,
    ZombieDogMode,
    _zombie_dog_default_movement,
)
from zombie_escape.entities.zombie_movement import (
    _zombie_wall_hug_movement,
    _zombie_wander_movement,
)
from zombie_escape.entities_constants import ZombieKind
from zombie_escape.level_constants import (
    DEFAULT_CELL_SIZE,
    DEFAULT_GRID_COLS,
    DEFAULT_GRID_ROWS,
)
from zombie_escape.models import LevelLayout


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def _make_layout(*, fire_floor_cells: set[tuple[int, int]]) -> LevelLayout:
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
        fire_floor_cells=fire_floor_cells,
        puddle_cells=set(),
        bevel_corners={},
        moving_floor_cells={},
    )


def test_zombie_wander_avoids_fire_floor_cell() -> None:
    _init_pygame()
    zombie = Zombie(
        5 * DEFAULT_CELL_SIZE + DEFAULT_CELL_SIZE // 2,
        5 * DEFAULT_CELL_SIZE + DEFAULT_CELL_SIZE // 2,
        kind=ZombieKind.NORMAL,
    )
    zombie.wander_angle = 0.0
    zombie.last_wander_change_time = 0
    zombie.wander_change_interval = 100000
    layout = _make_layout(fire_floor_cells={(6, 5)})

    move_x, move_y = _zombie_wander_movement(
        zombie,
        DEFAULT_CELL_SIZE,
        layout,
        now_ms=0,
    )
    next_cell = (
        int((zombie.x + move_x) // DEFAULT_CELL_SIZE),
        int((zombie.y + move_y) // DEFAULT_CELL_SIZE),
    )
    assert next_cell != (6, 5)


def test_zombie_dog_wander_avoids_fire_floor_cell() -> None:
    _init_pygame()
    zombie_dog = ZombieDog(
        5 * DEFAULT_CELL_SIZE + DEFAULT_CELL_SIZE // 2,
        5 * DEFAULT_CELL_SIZE + DEFAULT_CELL_SIZE // 2,
    )
    zombie_dog.mode = ZombieDogMode.WANDER
    zombie_dog.wander_angle = 0.0
    zombie_dog.wander_change_time = 0
    layout = _make_layout(fire_floor_cells={(6, 5)})

    move_x, move_y = _zombie_dog_default_movement(
        zombie_dog,
        DEFAULT_CELL_SIZE,
        layout,
        (9999.0, 9999.0),
        [],
        [],
        now_ms=0,
    )
    next_cell = (
        int((zombie_dog.x + move_x) // DEFAULT_CELL_SIZE),
        int((zombie_dog.y + move_y) // DEFAULT_CELL_SIZE),
    )
    assert next_cell != (6, 5)


def test_wall_hugger_treats_fire_floor_as_wall_probe() -> None:
    _init_pygame()
    zombie = Zombie(
        5 * DEFAULT_CELL_SIZE + DEFAULT_CELL_SIZE // 2,
        5 * DEFAULT_CELL_SIZE + DEFAULT_CELL_SIZE // 2,
        kind=ZombieKind.WALL_HUGGER,
    )
    zombie.wall_hug_side = 0.0
    zombie.wall_hug_angle = 0.0
    layout = _make_layout(fire_floor_cells={(6, 5)})

    _zombie_wall_hug_movement(
        zombie,
        DEFAULT_CELL_SIZE,
        layout,
        (9999.0, 9999.0),
        [],
        [],
        now_ms=123,
    )
    assert zombie.wall_hug_side != 0.0
    assert zombie.wall_hug_last_wall_time == 123
