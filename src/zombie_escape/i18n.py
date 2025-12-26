"""Lightweight python-i18n wrapper for runtime language switches."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Iterable, Tuple

import i18n

DEFAULT_LANGUAGE = "en"


@dataclass(frozen=True)
class LanguageOption:
    code: str
    name: str


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
    qualified_key = key if key.startswith("ui.") else f"ui.{key}"
    return i18n.t(qualified_key, default=key, **kwargs)


__all__ = [
    "DEFAULT_LANGUAGE",
    "LanguageOption",
    "get_language",
    "get_language_name",
    "language_options",
    "set_language",
    "translate",
]
