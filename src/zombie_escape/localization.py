"""Lightweight python-i18n wrapper for runtime language switches."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from .font_utils import clear_font_cache

import i18n

DEFAULT_LANGUAGE = "en"

DEFAULT_FONT_RESOURCE = "assets/fonts/Silkscreen-Regular.ttf"
DEFAULT_FONT_SCALE = 0.7


@dataclass(frozen=True)
class LanguageOption:
    code: str
    name: str


@dataclass(frozen=True)
class FontSettings:
    resource: str | None
    scale: float = 1.0

    def scaled_size(self, base_size: int) -> int:
        return max(1, round(base_size * self.scale))


_LANGUAGE_OPTIONS: tuple[LanguageOption, ...] | None = None
_LOCALE_DATA: dict[str, dict[str, Any]] = {}

_CURRENT_LANGUAGE = DEFAULT_LANGUAGE
_CONFIGURED = False


def _configure_backend() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    base_path = resources.files("zombie_escape").joinpath("locales")
    load_path = str(base_path)
    if load_path not in i18n.load_path:
        i18n.load_path.append(load_path)
    i18n.set("filename_format", "{namespace}.{locale}.{format}")
    i18n.set("file_format", "json")
    i18n.set("fallback", DEFAULT_LANGUAGE)
    i18n.set("error_on_missing_translation", False)
    i18n.set("enable_memoization", True)
    _CONFIGURED = True


def _normalize_language(code: str | None) -> str:
    if code:
        for option in _get_language_options():
            if option.code == code:
                return option.code
    return DEFAULT_LANGUAGE


def set_language(code: str | None) -> str:
    """Configure the active language, returning the resolved code."""
    global _CURRENT_LANGUAGE
    _configure_backend()
    resolved = _normalize_language(code)
    i18n.set("locale", resolved)
    _CURRENT_LANGUAGE = resolved
    clear_font_cache()
    return resolved


def get_language() -> str:
    return _CURRENT_LANGUAGE


def language_options() -> tuple[LanguageOption, ...]:
    return _get_language_options()


def get_language_name(code: str) -> str:
    for option in _get_language_options():
        if option.code == code:
            return option.name
    for option in _get_language_options():
        if option.code == DEFAULT_LANGUAGE:
            return option.name
    return code or DEFAULT_LANGUAGE


def translate(key: str, **kwargs: Any) -> str:
    if not _CONFIGURED:
        set_language(_CURRENT_LANGUAGE)
    qualified_key = _qualify_key(key)
    return i18n.t(qualified_key, default=key, **kwargs)


def translate_dict(key: str) -> dict[str, Any]:
    if not _CONFIGURED:
        set_language(_CURRENT_LANGUAGE)
    qualified_key = _qualify_key(key)
    result = i18n.t(qualified_key, default={})
    return result if isinstance(result, dict) else {}


def translate_list(key: str) -> list[Any]:
    if not _CONFIGURED:
        set_language(_CURRENT_LANGUAGE)
    result = _lookup_locale_value(key)
    return result if isinstance(result, list) else []


def get_font_settings(*, name: str = "primary") -> FontSettings:
    _get_language_options()  # ensure locale data is loaded
    locale_data = _LOCALE_DATA.get(_CURRENT_LANGUAGE) or _LOCALE_DATA.get(
        DEFAULT_LANGUAGE, {}
    )
    fonts = locale_data.get("fonts", {}) if isinstance(locale_data, dict) else {}
    data = fonts.get(name, {}) if isinstance(fonts, dict) else {}
    resource = data.get("resource") or DEFAULT_FONT_RESOURCE
    scale_raw = data.get("scale", DEFAULT_FONT_SCALE)
    try:
        scale = float(scale_raw)
    except (TypeError, ValueError):
        scale = DEFAULT_FONT_SCALE
    return FontSettings(resource=resource, scale=scale)


def _qualify_key(key: str) -> str:
    return key if key.startswith("ui.") else f"ui.{key}"


def _lookup_locale_value(key: str) -> Any:
    locale_data = _LOCALE_DATA.get(_CURRENT_LANGUAGE) or _LOCALE_DATA.get(
        DEFAULT_LANGUAGE, {}
    )
    if not isinstance(locale_data, dict):
        return None
    qualified = _qualify_key(key)
    path = qualified.split(".")
    if path and path[0] == "ui":
        path = path[1:]
    current: Any = locale_data
    for segment in path:
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
        if current is None:
            return None
    return current


def _get_language_options() -> tuple[LanguageOption, ...]:
    global _LANGUAGE_OPTIONS
    if _LANGUAGE_OPTIONS is not None:
        return _LANGUAGE_OPTIONS

    base = resources.files("zombie_escape").joinpath("locales")
    try:
        entries = list(base.iterdir())
    except FileNotFoundError:
        entries = []

    english_entry = base.joinpath("ui.en.json")
    if not english_entry.exists():
        raise FileNotFoundError("Missing required locale file: ui.en.json")

    options: list[LanguageOption] = []
    _LOCALE_DATA.clear()
    for entry in entries:
        name = entry.name
        if not name.startswith("ui.") or not name.endswith(".json"):
            continue
        code = name[3:-5]
        try:
            with resources.as_file(entry) as path:
                data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        locale_data = data.get(code, {}) if isinstance(data, dict) else {}
        _LOCALE_DATA[code] = locale_data if isinstance(locale_data, dict) else {}
        lang_name = (
            locale_data.get("meta", {}).get("language_name")
            if isinstance(locale_data, dict)
            else None
        )
        options.append(LanguageOption(code=code, name=lang_name or code))

    if not options:
        options.append(LanguageOption(code=DEFAULT_LANGUAGE, name="English"))

    options.sort(key=lambda opt: (0 if opt.code == "en" else 1, opt.code))
    _LANGUAGE_OPTIONS = tuple(options)
    return _LANGUAGE_OPTIONS


__all__ = [
    "DEFAULT_LANGUAGE",
    "FontSettings",
    "LanguageOption",
    "get_font_settings",
    "get_language",
    "get_language_name",
    "language_options",
    "set_language",
    "translate",
    "translate_list",
    "translate_dict",
]
