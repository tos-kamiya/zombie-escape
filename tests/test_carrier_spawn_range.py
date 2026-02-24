import pytest

from zombie_escape.gameplay.spawn import _select_carrier_spawn_cell
from zombie_escape.level_constants import DEFAULT_CELL_SIZE
from zombie_escape.models import LevelLayout

pygame = pytest.importorskip("pygame")


def _layout(
    *,
    cols: int,
    rows: int,
    outer: set[tuple[int, int]] | None = None,
    walls: set[tuple[int, int]] | None = None,
    steel: set[tuple[int, int]] | None = None,
    outside: set[tuple[int, int]] | None = None,
) -> LevelLayout:
    return LevelLayout(
        field_rect=pygame.Rect(0, 0, cols * DEFAULT_CELL_SIZE, rows * DEFAULT_CELL_SIZE),
        grid_cols=cols,
        grid_rows=rows,
        outside_cells=outside or set(),
        walkable_cells=[],
        outer_wall_cells=outer or set(),
        wall_cells=walls or set(),
        steel_beam_cells=steel or set(),
        pitfall_cells=set(),
        car_walkable_cells=set(),
        car_spawn_cells=[],
        fall_spawn_cells=set(),
        spiky_plant_cells=set(),
    )


def test_select_carrier_spawn_cell_avoids_outer_wall_on_axis() -> None:
    layout = _layout(cols=6, rows=4, outer={(0, 1), (1, 1)})
    selected = _select_carrier_spawn_cell(
        start_cell=(0, 1),
        axis="x",
        layout=layout,
        pitfall_cells=set(),
    )
    assert selected == (2, 1)


def test_select_carrier_spawn_cell_avoids_reinforced_wall_on_axis() -> None:
    layout = _layout(cols=5, rows=6, steel={(2, 2), (2, 3)})
    selected = _select_carrier_spawn_cell(
        start_cell=(2, 2),
        axis="y",
        layout=layout,
        pitfall_cells=set(),
    )
    assert selected == (2, 1)


def test_select_carrier_spawn_cell_returns_none_if_axis_fully_blocked() -> None:
    layout = _layout(cols=4, rows=3, walls={(x, 1) for x in range(4)})
    selected = _select_carrier_spawn_cell(
        start_cell=(2, 1),
        axis="x",
        layout=layout,
        pitfall_cells=set(),
    )
    assert selected is None
