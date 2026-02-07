from __future__ import annotations

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator

import pygame

_FONT_CACHE: dict[tuple[str | None, int], pygame.font.Font] = {}
_FONT_META: dict[int, tuple[str | None, int]] = {}


@contextmanager
def _resource_path(resource: str | None) -> Iterator[Path | None]:
    if not resource:
        yield None
        return

    try:
        font = resources.files("zombie_escape")
        for part in Path(resource).parts:
            font = font.joinpath(part)
        with resources.as_file(font) as path:
            yield path
    except (FileNotFoundError, ModuleNotFoundError):
        yield None


def load_font(resource: str | None, size: int) -> pygame.font.Font:
    """Load and cache a pygame font for the given resource and size."""
    normalized_size = max(1, int(size))
    cache_key = (resource, normalized_size)
    cached = _FONT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with _resource_path(resource) as path:
        font = pygame.font.Font(str(path) if path else None, normalized_size)

    _FONT_CACHE[cache_key] = font
    _FONT_META[id(font)] = (resource, normalized_size)
    return font


def render_text_surface(
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    *,
    line_height_scale: float = 1.0,
) -> pygame.Surface:
    surface = font.render(text, False, color).convert_alpha()
    line_height = int(round(font.get_linesize() * max(0.0, line_height_scale)))
    if line_height <= 0 or line_height <= surface.get_height():
        return surface
    padded = pygame.Surface((surface.get_width(), line_height), pygame.SRCALPHA)
    top_pad = max(0, (line_height - surface.get_height()) // 2)
    padded.blit(surface, (0, top_pad))
    return padded


def clear_font_cache() -> None:
    _FONT_CACHE.clear()
    _FONT_META.clear()
