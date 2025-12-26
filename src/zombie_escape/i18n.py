"""Lightweight python-i18n wrapper for runtime language switches."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Any, Tuple

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


SUPPORTED_LANGUAGES: Tuple[LanguageOption, ...] = (
    LanguageOption(code="en", name="English"),
)

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
        for option in SUPPORTED_LANGUAGES:
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
    return resolved


def get_language() -> str:
    return _CURRENT_LANGUAGE


def language_options() -> Tuple[LanguageOption, ...]:
    return SUPPORTED_LANGUAGES


def get_language_name(code: str) -> str:
    for option in SUPPORTED_LANGUAGES:
        if option.code == code:
            return option.name
    for option in SUPPORTED_LANGUAGES:
        if option.code == DEFAULT_LANGUAGE:
            return option.name
    return code or DEFAULT_LANGUAGE


def translate(key: str, **kwargs) -> str:
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


def get_font_settings(name: str = "primary") -> FontSettings:
    data = translate_dict(f"fonts.{name}")
    resource = data.get("resource") or DEFAULT_FONT_RESOURCE
    scale_raw = data.get("scale", DEFAULT_FONT_SCALE)
    try:
        scale = float(scale_raw)
    except (TypeError, ValueError):
        scale = 1.0
    return FontSettings(resource=resource, scale=scale)


def _qualify_key(key: str) -> str:
    return key if key.startswith("ui.") else f"ui.{key}"


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
    "translate_dict",
]
