"""Screen framework utilities for zombie_escape.

This module defines common types that allow each screen (title, settings,
gameplay, game over, etc.) to communicate transitions in a consistent way.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import pygame
from pygame import surface

try:  # pragma: no cover - version fallback not critical for tests
    from ..__about__ import __version__
except Exception:  # pragma: no cover - fallback version
    __version__ = "0.0.0-unknown"
from ..screen_constants import (
    DEFAULT_WINDOW_SCALE,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WINDOW_SCALE_MAX,
    WINDOW_SCALE_MIN,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..models import GameData, Stage


class ScreenID(Enum):
    """Identifiers for the major screens in the game."""

    TITLE = "title"
    SETTINGS = "settings"
    GAMEPLAY = "gameplay"
    GAME_OVER = "game_over"
    EXIT = "exit"


@dataclass(frozen=True)
class ScreenTransition:
    """Represents the next screen to display and optional payload data."""

    next_screen: ScreenID
    stage: Stage | None = None
    game_data: GameData | None = None
    config: dict | None = None
    seed: int | None = None
    seed_text: str | None = None
    seed_is_auto: bool = False


current_window_scale = DEFAULT_WINDOW_SCALE  # Applied to the OS window only
current_maximized = False
last_window_scale = DEFAULT_WINDOW_SCALE
current_window_size = (
    int(SCREEN_WIDTH * DEFAULT_WINDOW_SCALE),
    int(SCREEN_HEIGHT * DEFAULT_WINDOW_SCALE),
)
last_logged_window_size = current_window_size

__all__ = [
    "ScreenID",
    "ScreenTransition",
    "present",
    "apply_window_scale",
    "nudge_window_scale",
    "toggle_fullscreen",
    "sync_window_size",
]


def present(logical_surface: surface.Surface) -> None:
    """Scale the logical surface directly to the window and flip buffers."""
    window = pygame.display.get_surface()
    if window is None:
        return
    window_size = _fetch_window_size(window)
    _update_window_size(window_size, source="frame")
    logical_size = logical_surface.get_size()
    if window_size == logical_size:
        window.blit(logical_surface, (0, 0))
    else:
        # Preserve aspect ratio with letterboxing.
        scale_x = window_size[0] / max(1, logical_size[0])
        scale_y = window_size[1] / max(1, logical_size[1])
        scale = min(scale_x, scale_y)
        scaled_width = max(1, int(logical_size[0] * scale))
        scaled_height = max(1, int(logical_size[1] * scale))
        window.fill((0, 0, 0))
        if (scaled_width, scaled_height) == logical_size:
            scaled_surface = logical_surface
        else:
            scaled_surface = pygame.transform.scale(
                logical_surface, (scaled_width, scaled_height)
            )
        offset_x = (window_size[0] - scaled_width) // 2
        offset_y = (window_size[1] - scaled_height) // 2
        window.blit(scaled_surface, (offset_x, offset_y))
    pygame.display.flip()


def apply_window_scale(
    scale: float, *, game_data: "GameData | None" = None
) -> surface.Surface:
    """Resize the OS window; logical render surface stays constant."""
    global current_window_scale, current_maximized, last_window_scale

    clamped_scale = max(WINDOW_SCALE_MIN, min(WINDOW_SCALE_MAX, scale))
    current_window_scale = clamped_scale
    last_window_scale = clamped_scale
    current_maximized = False

    window_width = max(1, int(SCREEN_WIDTH * current_window_scale))
    window_height = max(1, int(SCREEN_HEIGHT * current_window_scale))

    new_window = pygame.display.set_mode(
        (window_width, window_height), pygame.RESIZABLE
    )
    _update_window_size((window_width, window_height), source="apply_scale")
    _update_window_caption(window_width, window_height)

    if game_data is not None:
        game_data.state.overview_created = False

    return new_window


def nudge_window_scale(
    multiplier: float, *, game_data: "GameData | None" = None
) -> surface.Surface:
    """Scale the window relative to the current zoom level."""
    target_scale = current_window_scale * multiplier
    return apply_window_scale(target_scale, game_data=game_data)


def toggle_fullscreen(
    *, game_data: "GameData | None" = None
) -> surface.Surface | None:
    """Toggle a maximized window without persisting the setting."""
    global current_maximized, last_window_scale
    if current_maximized:
        current_maximized = False
        window_width = max(1, int(SCREEN_WIDTH * last_window_scale))
        window_height = max(1, int(SCREEN_HEIGHT * last_window_scale))
        window = pygame.display.set_mode(
            (window_width, window_height), pygame.RESIZABLE
        )
        _restore_window()
        _update_window_caption(window_width, window_height)
        _update_window_size((window_width, window_height), source="toggle_windowed")
    else:
        last_window_scale = current_window_scale
        current_maximized = True
        window = pygame.display.set_mode(_fetch_window_size(None), pygame.RESIZABLE)
        _maximize_window()
        window_width, window_height = _fetch_window_size(window)
        _update_window_caption(window_width, window_height)
        _update_window_size((window_width, window_height), source="toggle_fullscreen")
    pygame.mouse.set_visible(not current_maximized)
    if game_data is not None:
        game_data.state.overview_created = False
    return window


def sync_window_size(
    event: pygame.event.Event, *, game_data: "GameData | None" = None
) -> None:
    """Synchronize tracked window size with SDL window events."""
    global current_window_scale, last_window_scale
    size = getattr(event, "size", None)
    if not size:
        width = getattr(event, "x", None)
        height = getattr(event, "y", None)
        if width is not None and height is not None:
            size = (width, height)
    if not size:
        return
    window_width, window_height = _normalize_window_size(size)
    _update_window_size(
        (window_width, window_height), source="window_event"
    )
    if not current_maximized:
        scale_x = window_width / max(1, SCREEN_WIDTH)
        scale_y = window_height / max(1, SCREEN_HEIGHT)
        scale = max(WINDOW_SCALE_MIN, min(WINDOW_SCALE_MAX, min(scale_x, scale_y)))
        current_window_scale = scale
        last_window_scale = scale
    _update_window_caption(window_width, window_height)
    if game_data is not None:
        game_data.state.overview_created = False


def _fetch_window_size(window: surface.Surface | None) -> tuple[int, int]:
    if hasattr(pygame.display, "get_window_size"):
        size = pygame.display.get_window_size()
        if size != (0, 0):
            return _normalize_window_size(size)
    if window is not None:
        return _normalize_window_size(window.get_size())
    window_width = max(1, int(SCREEN_WIDTH * last_window_scale))
    window_height = max(1, int(SCREEN_HEIGHT * last_window_scale))
    return window_width, window_height


def _normalize_window_size(size: tuple[int, int]) -> tuple[int, int]:
    width = max(1, int(size[0]))
    height = max(1, int(size[1]))
    return width, height


def _update_window_size(size: tuple[int, int], *, source: str) -> None:
    global current_window_size, last_logged_window_size
    current_window_size = size
    if size != last_logged_window_size:
        print(f"WINDOW_SIZE {source}={size[0]}x{size[1]}")
        last_logged_window_size = size


def _update_window_caption(window_width: int, window_height: int) -> None:
    pygame.display.set_caption(f"Zombie Escape ({window_width}x{window_height})")


def _maximize_window() -> None:
    try:
        from pygame import _sdl2 as sdl2  # type: ignore[import-not-found]
    except Exception:
        return
    try:
        window = sdl2.Window.from_display_module()
    except Exception:
        return
    try:
        window.maximize()
    except Exception:
        return


def _restore_window() -> None:
    try:
        from pygame import _sdl2 as sdl2  # type: ignore[import-not-found]
    except Exception:
        return
    try:
        window = sdl2.Window.from_display_module()
    except Exception:
        return
    try:
        window.restore()
    except Exception:
        return
