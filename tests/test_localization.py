import importlib
import json
from importlib import resources
from types import ModuleType
from typing import Any

import pytest

import zombie_escape.localization as localization_module


@pytest.fixture()
def localization() -> ModuleType:
    """Reload localization module to reset cached state between tests."""
    return importlib.reload(localization_module)


def test_language_options_include_metadata(localization: object) -> None:
    options = localization.language_options()

    assert options[0].code == "en"
    assert any(opt.code == "ja" and opt.name == "日本語" for opt in options)


def test_get_font_settings_uses_locale_data(localization: object) -> None:
    localization.set_language("ja")

    settings = localization.get_font_settings(name="primary")

    assert settings.resource.endswith("misaki_gothic.ttf")
    assert settings.scale == pytest.approx(0.7)
    assert settings.scaled_size(10) == 7


def test_translate_qualifies_key_and_falls_back(localization: object) -> None:
    localization.set_language("en")

    assert localization.translate("menu.settings") == "Settings"
    assert localization.translate("does_not_exist") == "does_not_exist"


def _load_locale_payload(code: str) -> dict[str, Any]:
    locale_dir = resources.files("zombie_escape").joinpath("locales")
    entry = locale_dir.joinpath(f"ui.{code}.json")
    with resources.as_file(entry) as path:
        payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get(code)
    if not isinstance(data, dict):
        raise AssertionError(f"Locale '{code}' missing top-level '{code}' entry")
    return data


def _assert_same_structure(reference: Any, candidate: Any, path: str) -> None:
    if isinstance(reference, dict):
        assert isinstance(candidate, dict), f"{path} expected dict"
        assert set(candidate.keys()) == set(reference.keys()), f"{path} keys differ"
        for key in reference:
            _assert_same_structure(reference[key], candidate[key], f"{path}.{key}")
    else:
        assert not isinstance(candidate, dict), f"{path} expected non-dict value"


def test_locale_files_match_english_schema() -> None:
    english_payload = _load_locale_payload("en")
    locale_dir = resources.files("zombie_escape").joinpath("locales")
    for entry in locale_dir.iterdir():
        name = entry.name
        if not name.startswith("ui.") or not name.endswith(".json"):
            continue
        code = name[3:-5]
        payload = _load_locale_payload(code)
        _assert_same_structure(english_payload, payload, code)
