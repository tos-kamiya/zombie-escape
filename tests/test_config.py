import json
from pathlib import Path

from zombie_escape import config


def test_deep_merge_handles_nested_dicts_without_mutating_inputs() -> None:
    base = {"footprints": {"enabled": True}, "fast_zombies": {"ratio": 0.1}}
    override = {
        "footprints": {"enabled": False},
        "fast_zombies": {"enabled": True},
        "car_hint": {"delay_ms": 1000},
    }

    merged = config._deep_merge(base, override)

    assert merged["footprints"]["enabled"] is False
    assert merged["fast_zombies"]["ratio"] == 0.1
    assert merged["fast_zombies"]["enabled"] is True
    assert merged["car_hint"]["delay_ms"] == 1000

    assert base["footprints"]["enabled"] is True
    assert "enabled" not in base["fast_zombies"]


def test_load_config_merges_defaults_with_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "fast_zombies": {"ratio": 0.5},
                "new_option": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )

    loaded, resolved_path = config.load_config(path=config_path)

    assert resolved_path == config_path
    assert loaded["fast_zombies"]["ratio"] == 0.5
    assert loaded["fast_zombies"]["enabled"] is False
    assert loaded["new_option"] == {"enabled": True}
    assert loaded is not config.DEFAULT_CONFIG


def test_load_config_falls_back_to_defaults_on_invalid_json(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("not valid json", encoding="utf-8")

    loaded, resolved_path = config.load_config(path=config_path)

    assert resolved_path == config_path
    assert loaded == config.DEFAULT_CONFIG
    assert loaded["fast_zombies"] is not config.DEFAULT_CONFIG["fast_zombies"]


def test_save_config_persists_to_disk(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    payload = {"debug": {"hide_pause_overlay": True}}

    config.save_config(payload, config_path)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved == payload
