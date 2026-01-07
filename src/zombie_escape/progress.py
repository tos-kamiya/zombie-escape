from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_data_dir

from .config import APP_NAME


def user_progress_path() -> Path:
    """Return the platform-specific progress file path."""
    return Path(user_data_dir(APP_NAME, APP_NAME)) / "progress.json"


def load_progress(*, path: Path | None = None) -> tuple[dict[str, int], Path]:
    """Load stage clear counts from disk, ignoring malformed entries."""
    progress_path = path or user_progress_path()
    progress: dict[str, int] = {}

    try:
        if progress_path.exists():
            loaded = json.loads(progress_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key, value in loaded.items():
                    if isinstance(key, str) and isinstance(value, int):
                        progress[key] = max(0, value)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load progress ({progress_path}): {exc}")

    return progress, progress_path


def save_progress(progress: dict[str, int], path: Path) -> None:
    """Persist stage clear counts to disk."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to save progress ({path}): {exc}")


def record_stage_clear(stage_id: str, *, path: Path | None = None) -> dict[str, int]:
    """Increment the clear count for a stage and persist it."""
    progress, progress_path = load_progress(path=path)
    progress[stage_id] = int(progress.get(stage_id, 0)) + 1
    save_progress(progress, progress_path)
    return progress
