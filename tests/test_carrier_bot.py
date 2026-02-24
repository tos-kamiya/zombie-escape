import pytest

from zombie_escape.entities.carrier_bot import CarrierBot
from zombie_escape.entities.material import Material
from zombie_escape.level_constants import (
    DEFAULT_CELL_SIZE,
    DEFAULT_GRID_COLS,
    DEFAULT_GRID_ROWS,
)
from zombie_escape.models import LevelLayout

pygame = pytest.importorskip("pygame")


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def _make_layout(*, width: int, height: int) -> LevelLayout:
    cols = max(1, width // DEFAULT_CELL_SIZE)
    rows = max(1, height // DEFAULT_CELL_SIZE)
    if cols <= 0:
        cols = DEFAULT_GRID_COLS
    if rows <= 0:
        rows = DEFAULT_GRID_ROWS
    return LevelLayout(
        field_rect=pygame.Rect(0, 0, width, height),
        grid_cols=cols,
        grid_rows=rows,
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


def test_carrier_bot_loads_only_after_overlap_and_reverses() -> None:
    _init_pygame()
    layout = _make_layout(width=200, height=200)
    bot = CarrierBot(25, 25, axis="x", direction_sign=1, speed=10.0)
    material = Material(55, 25)

    # Not overlapping yet: should just move forward.
    bot.update(
        [],
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        materials=[material],
    )
    assert bot.carried_material is None
    assert bot.rect.center == (35, 25)

    # Still not fully overlapping yet.
    bot.update(
        [],
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        materials=[material],
    )
    assert bot.carried_material is None
    assert bot.rect.center == (45, 25)

    # Fully overlapping tick: should load and reverse.
    bot.update(
        [],
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        materials=[material],
    )
    assert bot.carried_material is material
    assert material.carried_by is bot
    assert bot.direction == (-1, 0)
    assert bot.rect.center == (55, 25)


def test_carrier_bot_drops_material_when_blocked_then_reverses() -> None:
    _init_pygame()
    layout = _make_layout(width=100, height=100)
    bot = CarrierBot(95, 25, axis="x", direction_sign=1, speed=10.0)
    material = Material(95, 25)
    bot.carried_material = material
    material.carried_by = bot

    bot.update(
        [],
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        materials=[material],
    )

    assert bot.carried_material is None
    assert material.carried_by is None
    assert material.rect.center == (95, 25)
    assert bot.direction == (-1, 0)


def test_carrier_bot_moves_with_carried_material() -> None:
    _init_pygame()
    layout = _make_layout(width=200, height=200)
    bot = CarrierBot(25, 25, axis="x", direction_sign=1, speed=10.0)
    material = Material(25, 25)
    bot.carried_material = material
    material.carried_by = bot

    bot.update(
        [],
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        materials=[material],
    )

    assert bot.rect.center == (35, 25)
    assert material.rect.center == bot.rect.center


def test_carrier_bot_moves_away_after_drop_at_outer_wall() -> None:
    _init_pygame()
    layout = _make_layout(width=100, height=100)
    bot = CarrierBot(95, 25, axis="x", direction_sign=1, speed=10.0)
    material = Material(95, 25)
    bot.carried_material = material
    material.carried_by = bot

    bot.update(
        [],
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        materials=[material],
    )
    assert bot.direction == (-1, 0)
    assert material.carried_by is None
    assert bot.carried_material is None
    assert material.rect.center == (95, 25)
    bot.update(
        [],
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        materials=[material],
    )
    assert bot.rect.centerx < 95
    assert bot.carried_material is None


def test_carrier_bot_does_not_repickup_dropped_material_until_separated() -> None:
    _init_pygame()
    layout = _make_layout(width=100, height=100)
    bot = CarrierBot(95, 25, axis="x", direction_sign=1, speed=10.0)
    carried = Material(95, 25)
    bot.carried_material = carried
    carried.carried_by = bot

    bot.update(
        [],
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        materials=[carried],
    )

    assert bot.carried_material is None
    assert carried.carried_by is None
    assert carried.rect.center == bot.rect.center
    # Next tick while still close: should not instantly re-pick.
    bot.update(
        [],
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        materials=[carried],
    )
    assert bot.carried_material is None
