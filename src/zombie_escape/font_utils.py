from __future__ import annotations

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator

import pygame

_FONT_CACHE: dict[tuple[str | None, int], pygame.font.Font] = {}
_FONT_META: dict[int, tuple[str | None, int]] = {}
_TEXT_RENDER_SCALE = 7
_TEXT_BLUR_OFFSET = 1
_TEXT_BLUR_ALPHA = 122


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


def render_text_scaled_font(
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
) -> pygame.Surface:
    """Render text with a provided font, supersampling when possible."""
    meta = _FONT_META.get(id(font))
    if meta is None:
        return font.render(text, True, color)
    resource, size = meta
    high_size = max(1, int(round(size * _TEXT_RENDER_SCALE)))
    font_high = load_font(resource, high_size)
    high_surface = font_high.render(text, True, color).convert_alpha()
    crisp_surface = font_high.render(text, True, color).convert_alpha()
    crisp_surface.set_alpha(_TEXT_BLUR_ALPHA)
    high_surface.blit(crisp_surface, (_TEXT_BLUR_OFFSET, _TEXT_BLUR_OFFSET))
    target_width = max(1, int(round(high_surface.get_width() / _TEXT_RENDER_SCALE)))
    target_height = max(1, int(round(high_surface.get_height() / _TEXT_RENDER_SCALE)))
    return pygame.transform.smoothscale(high_surface, (target_width, target_height))


def render_text_unscaled(
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    *,
    line_height_scale: float = 1.0,
) -> pygame.Surface:
    """Render text without supersampling for realtime HUD use."""
    surface = font.render(text, False, color).convert_alpha()
    line_height = int(round(font.get_linesize() * max(0.0, line_height_scale)))
    if line_height <= 0 or line_height <= surface.get_height():
        return surface
    padded = pygame.Surface((surface.get_width(), line_height), pygame.SRCALPHA)
    top_pad = max(0, (line_height - surface.get_height()) // 2)
    padded.blit(surface, (0, top_pad))
    return padded


def blit_text_scaled_font(
    target: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    **rect_kwargs: int | tuple[int, int],
) -> pygame.Rect:
    """Render scaled text with a provided font and blit it to target."""
    surface = render_text_scaled_font(
        font,
        text,
        color,
    )
    rect = surface.get_rect(**rect_kwargs)
    target.blit(surface, rect)
    return rect


def clear_font_cache() -> None:
    _FONT_CACHE.clear()
    _FONT_META.clear()
