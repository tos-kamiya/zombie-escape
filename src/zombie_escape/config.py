import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Tuple

from platformdirs import user_config_dir

APP_NAME = "ZombieEscape"

# Defaults for all configurable options
DEFAULT_CONFIG: Dict[str, Any] = {
    "footprints": {"enabled": True},
    "fast_zombies": {"enabled": False, "ratio": 0.1},
    "car_hint": {"enabled": True, "delay_ms": 180_000},
    "flashlight": {"enabled": True, "bonus_scale": 1.35},
    "steel_beams": {"enabled": False, "chance": 0.05},
    "debug": {"hide_pause_overlay": False},
}


def user_config_path() -> Path:
    """Return the platform-specific config file path."""
    return Path(user_config_dir(APP_NAME, APP_NAME)) / "config.json"


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge dictionaries, with override winning on conflicts."""
    merged: Dict[str, Any] = deepcopy(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def load_config(path: Path | None = None) -> Tuple[Dict[str, Any], Path]:
    """Load config from disk, falling back to defaults on errors."""
    config_path = path or user_config_path()
    config: Dict[str, Any] = deepcopy(DEFAULT_CONFIG)

    try:
        if config_path.exists():
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config = _deep_merge(config, loaded)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load config ({config_path}): {exc}")

    return config, config_path


def save_config(config: Dict[str, Any], path: Path | None = None) -> None:
    """Persist config to disk, creating parent dirs as needed."""
    config_path = path or user_config_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to save config ({config_path}): {exc}")
