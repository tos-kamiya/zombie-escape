import pytest

from zombie_escape.entities import PatrolBot, Player
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


def _make_layout(
    *, puddle_cells: set[tuple[int, int]] | None = None
) -> LevelLayout:
    if puddle_cells is None:
        puddle_cells = set()
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
        puddle_cells=puddle_cells,
        bevel_corners={},
        moving_floor_cells={},
    )


def _update_paused_bot(bot: PatrolBot, player: Player, now_ms: int) -> None:
    bot.update(
        [],
        player=player,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        layout=_make_layout(),
        now_ms=now_ms,
    )


def test_patrol_bot_ignores_held_input_without_neutral_frame() -> None:
    _init_pygame()
    bot = PatrolBot(100, 100)
    bot.direction = (0, 1)
    bot.pause_until_ms = 1_000
    player = Player(100, 100)
    player.alive = lambda: True
    player.update_facing_from_input(1.0, 0.0)

    _update_paused_bot(bot, player, now_ms=100)

    assert bot.direction == (0, 1)
    assert bot.indicator_mode == "auto"


def test_patrol_bot_accepts_direction_after_neutral_then_input() -> None:
    _init_pygame()
    bot = PatrolBot(100, 100)
    bot.direction = (0, 1)
    bot.pause_until_ms = 1_000
    player = Player(100, 100)
    player.alive = lambda: True

    player.update_facing_from_input(0.0, 0.0)
    _update_paused_bot(bot, player, now_ms=100)
    assert bot.direction == (0, 1)
    assert bot.indicator_mode == "waiting"

    player.update_facing_from_input(-1.0, 0.0)
    _update_paused_bot(bot, player, now_ms=120)
    assert bot.direction == (-1, 0)
    assert bot.indicator_mode == "player"


def test_patrol_bot_does_not_enter_puddle_cell() -> None:
    _init_pygame()
    cell_size = DEFAULT_CELL_SIZE
    bot = PatrolBot(
        5 * cell_size + cell_size / 2,
        5 * cell_size + cell_size / 2,
    )
    bot.direction = (1, 0)
    layout = _make_layout(puddle_cells={(6, 5)})

    bot.update(
        [],
        cell_size=cell_size,
        pitfall_cells=set(),
        layout=layout,
        now_ms=1_000,
    )

    assert (int(bot.x // cell_size), int(bot.y // cell_size)) != (6, 5)
