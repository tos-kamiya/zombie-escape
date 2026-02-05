from __future__ import annotations

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator

import pygame

_FONT_CACHE: dict[tuple[str | None, int], pygame.font.Font] = {}


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
    return font


def render_text_scaled(
    resource: str | None,
    size: int,
    text: str,
    color: tuple[int, int, int],
    *,
    scale_factor: int = 1,
    antialias: bool = False,
) -> pygame.Surface:
    """Render text, optionally supersampling then downscaling."""
    normalized_size = max(1, int(size))
    if scale_factor <= 1:
        font = load_font(resource, normalized_size)
        return font.render(text, antialias, color)
    high_size = max(1, int(round(normalized_size * scale_factor)))
    font_high = load_font(resource, high_size)
    high_surface = font_high.render(text, antialias, color)
    target_width = max(1, int(round(high_surface.get_width() / scale_factor)))
    target_height = max(1, int(round(high_surface.get_height() / scale_factor)))
    return pygame.transform.scale(high_surface, (target_width, target_height))


def clear_font_cache() -> None:
    _FONT_CACHE.clear()
