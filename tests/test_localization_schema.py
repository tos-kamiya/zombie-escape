from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def get_all_key_paths(d: dict[str, Any], prefix: str = "") -> set[str]:
    keys = set()
    for k, v in d.items():
        new_prefix = f"{prefix}.{k}" if prefix else k
        keys.add(new_prefix)
        if isinstance(v, dict):
            keys.update(get_all_key_paths(v, new_prefix))
    return keys


def test_ui_json_schemas_are_synchronized() -> None:
    """Ensure all ui.*.json files have identical key structures."""
    locales_dir = (
        Path(__file__).resolve().parents[1] / "src" / "zombie_escape" / "locales"
    )
    json_files = list(locales_dir.glob("ui.*.json"))
    assert len(json_files) >= 2, (
        f"Expected at least 2 ui.*.json files, found {len(json_files)}"
    )

    file_data = {}
    for path in json_files:
        lang_code = path.name.split(".")[1]
        data = json.loads(path.read_text(encoding="utf-8"))

        # 1. Check top-level key matches filename lang code
        assert lang_code in data, f"Top-level key '{lang_code}' missing in {path.name}"
        assert len(data) == 1, (
            f"Expected exactly one top-level key in {path.name}, found {list(data.keys())}"
        )

        # Remove the top-level language key for comparison
        file_data[lang_code] = data[lang_code]

    # 2. Compare key sets between all languages
    reference_lang = list(file_data.keys())[0]
    reference_keys = get_all_key_paths(file_data[reference_lang])

    for lang, data in file_data.items():
        if lang == reference_lang:
            continue

        current_keys = get_all_key_paths(data)

        missing_in_current = reference_keys - current_keys
        extra_in_current = current_keys - reference_keys

        errors = []
        if missing_in_current:
            errors.append(
                f"Missing keys in '{lang}' (present in '{reference_lang}'): {sorted(missing_in_current)}"
            )
        if extra_in_current:
            errors.append(
                f"Extra keys in '{lang}' (missing in '{reference_lang}'): {sorted(extra_in_current)}"
            )

        assert not errors, (
            f"Schema mismatch between '{reference_lang}' and '{lang}':\n"
            + "\n".join(errors)
        )


def test_ui_json_mandatory_sections() -> None:
    """Check for mandatory sections in each ui.*.json file."""
    locales_dir = (
        Path(__file__).resolve().parents[1] / "src" / "zombie_escape" / "locales"
    )
    json_files = list(locales_dir.glob("ui.*.json"))

    mandatory_sections = {
        "meta",
        "game",
        "fonts",
        "menu",
        "stages",
        "status",
        "hud",
        "game_over",
        "settings",
        "errors",
    }

    for path in json_files:
        lang_code = path.name.split(".")[1]
        data = json.loads(path.read_text(encoding="utf-8"))[lang_code]

        actual_sections = set(data.keys())
        missing = mandatory_sections - actual_sections
        assert not missing, f"Mandatory sections {missing} missing in {path.name}"
