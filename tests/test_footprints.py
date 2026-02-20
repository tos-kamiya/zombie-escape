from types import SimpleNamespace

from zombie_escape.gameplay.footprints import update_footprints


def _make_game_data(
    *,
    pos: tuple[float, float],
    now_ms: int,
    puddle_cells: set[tuple[int, int]],
    last_pos: tuple[int, int] | None,
) -> SimpleNamespace:
    state = SimpleNamespace(
        clock=SimpleNamespace(elapsed_ms=now_ms),
        footprints=[],
        puddle_splashes=[],
        last_footprint_pos=last_pos,
        last_puddle_splash_pos=None,
        footprint_visible_toggle=True,
    )
    player = SimpleNamespace(in_car=False, x=pos[0], y=pos[1])
    layout = SimpleNamespace(puddle_cells=puddle_cells)
    return SimpleNamespace(state=state, player=player, layout=layout, cell_size=50)


def test_update_footprints_skips_puddle_and_breaks_trail_segment() -> None:
    game_data = _make_game_data(
        pos=(60.0, 60.0),
        now_ms=1000,
        puddle_cells={(1, 1)},
        last_pos=(20, 20),
    )

    update_footprints(game_data, config={})

    assert game_data.state.footprints == []
    assert game_data.state.last_footprint_pos is None
    assert len(game_data.state.puddle_splashes) == 1


def test_update_footprints_restarts_after_puddle_gap() -> None:
    game_data = _make_game_data(
        pos=(60.0, 60.0),
        now_ms=1000,
        puddle_cells={(1, 1)},
        last_pos=(20, 20),
    )
    update_footprints(game_data, config={})

    game_data.player.x = 110.0
    game_data.player.y = 110.0
    game_data.state.clock.elapsed_ms = 2000
    update_footprints(game_data, config={})

    assert len(game_data.state.footprints) == 1
    assert game_data.state.footprints[0].pos == (110, 110)


def test_update_footprints_puddle_splash_uses_footprint_step_timing() -> None:
    game_data = _make_game_data(
        pos=(60.0, 60.0),
        now_ms=1000,
        puddle_cells={(1, 1), (2, 1), (3, 1)},
        last_pos=None,
    )
    update_footprints(game_data, config={})
    assert len(game_data.state.puddle_splashes) == 1

    game_data.player.x = 70.0
    game_data.player.y = 60.0
    game_data.state.clock.elapsed_ms = 1100
    update_footprints(game_data, config={})
    assert len(game_data.state.puddle_splashes) == 1

    game_data.player.x = 85.0
    game_data.player.y = 60.0
    game_data.state.clock.elapsed_ms = 1200
    update_footprints(game_data, config={})
    assert len(game_data.state.puddle_splashes) == 2
