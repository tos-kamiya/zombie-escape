from types import SimpleNamespace

from zombie_escape import gameplay
from zombie_escape.gameplay import spawn as gameplay_spawn


def _make_game_data(**state_overrides):
    stage = SimpleNamespace(
        endurance_stage=True,
        spawn_interval_ms=5000,
        exterior_spawn_weight=0.55,
        interior_spawn_weight=0.45,
    )
    default_state = {
        "game_over": False,
        "game_won": False,
        "endurance_goal_ms": 1000,
        "endurance_elapsed_ms": 0,
        "dawn_ready": False,
        "dawn_prompt_at": None,
        "dawn_carbonized": False,
        "time_accel_active": False,
        "last_zombie_spawn_time": 0,
    }
    default_state.update(state_overrides)
    state = SimpleNamespace(**default_state)
    dummy_group = SimpleNamespace(add=lambda *args, **kwargs: None)
    groups = SimpleNamespace(zombie_group=[], all_sprites=dummy_group)
    layout = SimpleNamespace(
        outside_cells=set(),
        walkable_cells=[],
        outer_wall_cells=set(),
    )
    player = SimpleNamespace(x=0, y=0)
    camera = SimpleNamespace()
    return SimpleNamespace(
        stage=stage,
        state=state,
        groups=groups,
        layout=layout,
        camera=camera,
        level_width=0,
        level_height=0,
        player=player,
    )


def test_update_survival_timer_marks_dawn_ready() -> None:
    game_data = _make_game_data(endurance_elapsed_ms=950)

    gameplay.update_endurance_timer(game_data, 100)

    assert game_data.state.endurance_elapsed_ms == 1000
    assert game_data.state.dawn_ready is True
    assert game_data.state.dawn_prompt_at is not None
    assert game_data.state.dawn_carbonized is True


def test_spawn_weighted_prefers_interior(monkeypatch) -> None:
    calls: list[str] = []

    def fake_interior(game_data, config):
        calls.append("interior")
        return object()

    def fake_exterior(game_data, config):
        calls.append("exterior")
        return object()

    monkeypatch.setattr(gameplay_spawn, "_spawn_nearby_zombie", fake_interior)
    monkeypatch.setattr(gameplay_spawn, "spawn_exterior_zombie", fake_exterior)

    game_data = _make_game_data()
    game_data.stage.interior_spawn_weight = 1.0
    game_data.stage.exterior_spawn_weight = 0.0

    spawned = gameplay.spawn_weighted_zombie(game_data, {})

    assert spawned is True
    assert calls[0] == "interior"
