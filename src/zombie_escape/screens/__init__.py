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
last_window_position: tuple[int, int] | None = None
current_window_size = (
    int(SCREEN_WIDTH * DEFAULT_WINDOW_SCALE),
    int(SCREEN_HEIGHT * DEFAULT_WINDOW_SCALE),
)
last_logged_window_size = current_window_size

__all__ = [
    "ScreenID",
    "ScreenTransition",
    "TITLE_FONT_SCALE",
    "TITLE_LINE_HEIGHT_SCALE",
    "TITLE_HEADER_Y",
    "TITLE_SECTION_TOP",
    "present",
    "present_direct",
    "apply_window_scale",
    "nudge_window_scale",
    "toggle_fullscreen",
    "sync_window_size",
]

TITLE_FONT_SCALE = 2
TITLE_LINE_HEIGHT_SCALE = 1.5
TITLE_HEADER_Y = 40
TITLE_SECTION_TOP = 70


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
            scaled_surface = pygame.transform.scale(logical_surface, (scaled_width, scaled_height))
        offset_x = (window_size[0] - scaled_width) // 2
        offset_y = (window_size[1] - scaled_height) // 2
        window.blit(scaled_surface, (offset_x, offset_y))
    pygame.display.flip()


def present_direct(screen: surface.Surface) -> None:
    """Flip the display without scaling; intended for direct window rendering."""
    window = pygame.display.get_surface()
    if window is None:
        return
    if window is not screen:
        window.blit(screen, (0, 0))
    pygame.display.flip()


def apply_window_scale(scale: float, *, game_data: "GameData | None" = None) -> surface.Surface:
    """Resize the OS window; logical render surface stays constant."""
    global current_window_scale, current_maximized, last_window_scale

    clamped_scale = max(WINDOW_SCALE_MIN, min(WINDOW_SCALE_MAX, scale))
    current_window_scale = clamped_scale
    last_window_scale = clamped_scale
    current_maximized = False

    window_width = max(1, int(SCREEN_WIDTH * current_window_scale))
    window_height = max(1, int(SCREEN_HEIGHT * current_window_scale))

    new_window = pygame.display.set_mode((window_width, window_height), pygame.RESIZABLE)
    _update_window_size((window_width, window_height), source="apply_scale")
    _update_window_caption()

    if game_data is not None:
        game_data.state.overview_created = False

    return new_window


def nudge_window_scale(multiplier: float, *, game_data: "GameData | None" = None) -> surface.Surface:
    """Scale the window relative to the current zoom level."""
    target_scale = current_window_scale * multiplier
    return apply_window_scale(target_scale, game_data=game_data)


def toggle_fullscreen(*, game_data: "GameData | None" = None) -> surface.Surface | None:
    """Toggle fullscreen without persisting the setting."""
    global current_maximized, last_window_scale, last_window_position
    if current_maximized:
        current_maximized = False
        window_width = max(1, int(SCREEN_WIDTH * last_window_scale))
        window_height = max(1, int(SCREEN_HEIGHT * last_window_scale))
        _set_sdl2_fullscreen(False, None)
        window = pygame.display.set_mode((window_width, window_height), pygame.RESIZABLE)
        if last_window_position is not None:
            _restore_window_position(last_window_position)
        _restore_window()
        _update_window_caption()
        _update_window_size((window_width, window_height), source="toggle_windowed")
    else:
        last_window_scale = current_window_scale
        last_window_position = _fetch_window_position()
        current_maximized = True
        display_index = _fetch_display_index()
        window = None
        if _set_sdl2_fullscreen(True, display_index):
            window = pygame.display.get_surface()
        if window is None:
            if display_index is None:
                window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN, display=display_index)
        window_width, window_height = _fetch_window_size(window)
        _update_window_caption()
        _update_window_size((window_width, window_height), source="toggle_fullscreen")
    pygame.mouse.set_visible(not current_maximized)
    if game_data is not None:
        game_data.state.overview_created = False
    return window


def sync_window_size(event: pygame.event.Event, *, game_data: "GameData | None" = None) -> None:
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
    _update_window_size((window_width, window_height), source="window_event")
    if not current_maximized:
        scale_x = window_width / max(1, SCREEN_WIDTH)
        scale_y = window_height / max(1, SCREEN_HEIGHT)
        scale = max(WINDOW_SCALE_MIN, min(WINDOW_SCALE_MAX, min(scale_x, scale_y)))
        current_window_scale = scale
        last_window_scale = scale
    _update_window_caption()
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


def _fetch_window_position() -> tuple[int, int] | None:
    try:
        from pygame import _sdl2 as sdl2  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        window = sdl2.Window.from_display_module()
    except Exception:
        return None
    try:
        position = window.position
    except Exception:
        return None
    if not position:
        return None
    return (int(position[0]), int(position[1]))


def _restore_window_position(position: tuple[int, int]) -> None:
    try:
        from pygame import _sdl2 as sdl2  # type: ignore[import-not-found]
    except Exception:
        return
    try:
        window = sdl2.Window.from_display_module()
    except Exception:
        return
    setter = getattr(window, "set_position", None)
    if setter is not None:
        try:
            setter(position)
            return
        except Exception:
            return
    try:
        window.position = position
    except Exception:
        return


def _fetch_display_index() -> int | None:
    try:
        from pygame import _sdl2 as sdl2  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        window = sdl2.Window.from_display_module()
    except Exception:
        return None

    display_index = _infer_display_index_from_position(window, sdl2)
    if display_index is not None:
        return display_index

    try:
        return window.get_display_index()
    except Exception:
        return None


def _infer_display_index_from_position(window: object, sdl2: object) -> int | None:
    try:
        position = window.position  # type: ignore[attr-defined]
    except Exception:
        return None
    if not position:
        return None

    center_x, center_y = _window_center_from_position(window, position)
    display_count = _get_display_count(sdl2)
    if display_count is None:
        return None

    for display_index in range(display_count):
        bounds = _get_display_bounds(sdl2, display_index)
        if bounds is None:
            continue
        x, y, width, height = bounds
        if x <= center_x < x + width and y <= center_y < y + height:
            return display_index
    return None


def _window_center_from_position(window: object, position: tuple[int, int]) -> tuple[int, int]:
    x, y = position
    try:
        width, height = window.size  # type: ignore[attr-defined]
    except Exception:
        width, height = _fetch_window_size(None)
    return x + width // 2, y + height // 2


def _get_display_count(sdl2: object) -> int | None:
    candidate = getattr(sdl2, "get_num_video_displays", None)
    if candidate is None:
        candidate = getattr(getattr(sdl2, "video", None), "get_num_video_displays", None)
    if candidate is None:
        return None
    try:
        return int(candidate())
    except Exception:
        return None


def _get_display_bounds(sdl2: object, display_index: int) -> tuple[int, int, int, int] | None:
    candidate = getattr(sdl2, "get_display_bounds", None)
    if candidate is None:
        candidate = getattr(getattr(sdl2, "video", None), "get_display_bounds", None)
    if candidate is None:
        return None
    try:
        bounds = candidate(display_index)
    except Exception:
        return None
    if bounds is None:
        return None
    if hasattr(bounds, "x"):
        return (int(bounds.x), int(bounds.y), int(bounds.w), int(bounds.h))
    if isinstance(bounds, (tuple, list)) and len(bounds) >= 4:
        return (int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3]))
    return None


def _set_sdl2_fullscreen(enable: bool, display_index: int | None) -> bool:
    try:
        from pygame import _sdl2 as sdl2  # type: ignore[import-not-found]
    except Exception:
        return False
    try:
        window = sdl2.Window.from_display_module()
    except Exception:
        return False

    if enable and display_index is not None:
        setter = getattr(window, "set_display_index", None)
        if setter is not None:
            try:
                setter(display_index)
            except Exception:
                pass

    if hasattr(window, "fullscreen"):
        try:
            window.fullscreen = enable
            return True
        except Exception:
            pass

    setter = getattr(window, "set_fullscreen", None)
    if setter is None:
        return False
    try:
        setter(enable)
        return True
    except Exception:
        pass

    if enable:
        for attr_name in ("WINDOW_FULLSCREEN_DESKTOP", "FULLSCREEN_DESKTOP", "WINDOW_FULLSCREEN"):
            mode = getattr(sdl2, attr_name, None)
            if mode is None:
                continue
            try:
                setter(mode)
                return True
            except Exception:
                continue
    return False


def _update_window_size(size: tuple[int, int], *, source: str) -> None:
    global current_window_size, last_logged_window_size
    current_window_size = size
    if size != last_logged_window_size:
        print(f"WINDOW_SIZE {source}={size[0]}x{size[1]}")
        last_logged_window_size = size


def _update_window_caption() -> None:
    pygame.display.set_caption("Zombie Escape")


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
