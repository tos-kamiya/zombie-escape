from __future__ import annotations

import json
from pathlib import Path


def test_all_json_files_parse() -> None:
    """Ensure every JSON file in the repo parses successfully."""
    repo_root = Path(__file__).resolve().parents[1]
    json_paths = sorted(repo_root.rglob("*.json"))
    assert json_paths, "No JSON files discovered to validate."
    failures: list[tuple[Path, Exception]] = []
    for path in json_paths:
        # Skip typical virtualenv/cache folders to keep the test focused on the project.
        parts = {part.lower() for part in path.parts}
        if ".venv" in parts or "node_modules" in parts or "dist" in parts:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - failure path for diagnostics
            failures.append((path, exc))
    assert not failures, "\n".join(f"{path}: {error}" for path, error in failures)
