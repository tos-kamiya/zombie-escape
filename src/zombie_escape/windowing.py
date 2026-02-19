"""Window and presentation helpers for zombie_escape."""

from __future__ import annotations

from typing import TYPE_CHECKING
import os

import pygame
from pygame import surface

from .screen_constants import (
    DEFAULT_WINDOW_SCALE,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WINDOW_SCALE_MAX,
    WINDOW_SCALE_MIN,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .models import GameData

current_window_scale = DEFAULT_WINDOW_SCALE  # Applied to the OS window only
current_maximized = False
last_window_scale = DEFAULT_WINDOW_SCALE
last_window_position: tuple[int, int] | None = None
current_window_size = (
    int(SCREEN_WIDTH * DEFAULT_WINDOW_SCALE),
    int(SCREEN_HEIGHT * DEFAULT_WINDOW_SCALE),
)
last_logged_window_size = current_window_size
_scaled_logical_size = (SCREEN_WIDTH, SCREEN_HEIGHT)
_WINDOW_SCALE_COOLDOWN_MS = 500
_last_window_scale_apply_ms: int | None = None
_pending_window_scale: float | None = None
_pending_window_scale_game_data: "GameData | None" = None
_VSYNC_ENV = os.environ.get("ZOMBIE_ESCAPE_VSYNC")
_VSYNC_PREFERENCE: int | None
if _VSYNC_ENV is None:
    _VSYNC_PREFERENCE = None
else:
    _VSYNC_PREFERENCE = 1 if _VSYNC_ENV not in ("0", "false", "False") else 0

__all__ = [
    "present",
    "apply_window_scale",
    "prime_scaled_logical_size",
    "nudge_window_scale",
    "nudge_menu_window_scale",
    "toggle_fullscreen",
    "sync_window_size",
    "adjust_menu_logical_size",
    "set_scaled_logical_size",
]


def present(logical_surface: surface.Surface) -> None:
    """Scale the logical surface directly to the window and flip buffers."""
    _maybe_apply_pending_window_scale()
    window = pygame.display.get_surface()
    if window is None:
        return
    window_size = _fetch_window_size(window)
    _update_window_size(window_size, source="frame")
    logical_size = logical_surface.get_size()
    if _use_scaled_display():
        target_size = window.get_size()
        if logical_size == target_size:
            scaled_surface = logical_surface
        elif (
            logical_size[0] * 2 == target_size[0]
            and logical_size[1] * 2 == target_size[1]
        ):
            scaled_surface = pygame.transform.scale2x(logical_surface)
        else:
            scaled_surface = pygame.transform.scale(logical_surface, target_size)
        window.blit(scaled_surface, (0, 0))
    elif window_size == logical_size:
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
    global \
        _last_window_scale_apply_ms, \
        _pending_window_scale, \
        _pending_window_scale_game_data

    now = pygame.time.get_ticks()
    if pygame.display.get_surface() is None:
        _last_window_scale_apply_ms = now
        _pending_window_scale = None
        _pending_window_scale_game_data = None
        return _apply_window_scale_now(scale, game_data=game_data)
    if (
        _last_window_scale_apply_ms is not None
        and now - _last_window_scale_apply_ms < _WINDOW_SCALE_COOLDOWN_MS
    ):
        _pending_window_scale = scale
        _pending_window_scale_game_data = game_data
        window = pygame.display.get_surface()
        return window if window is not None else pygame.Surface((1, 1))
    _last_window_scale_apply_ms = now
    _pending_window_scale = None
    _pending_window_scale_game_data = None
    return _apply_window_scale_now(scale, game_data=game_data)


def _apply_window_scale_now(
    scale: float, *, game_data: "GameData | None" = None
) -> surface.Surface:
    global current_window_scale, current_maximized, last_window_scale

    clamped_scale = max(WINDOW_SCALE_MIN, min(WINDOW_SCALE_MAX, scale))
    current_window_scale = clamped_scale
    last_window_scale = clamped_scale
    current_maximized = False

    window_width = max(1, int(SCREEN_WIDTH * current_window_scale))
    window_height = max(1, int(SCREEN_HEIGHT * current_window_scale))

    flags = pygame.RESIZABLE
    if _use_scaled_display():
        flags |= pygame.SCALED
        new_window = _set_mode(_scaled_logical_size, flags)
        _set_window_size((window_width, window_height))
    else:
        new_window = _set_mode((window_width, window_height), flags)
    _update_window_size((window_width, window_height), source="apply_scale")
    _update_window_caption()

    if game_data is not None:
        game_data.state.overview_created = False

    return new_window


def prime_scaled_logical_size(size: tuple[int, int]) -> None:
    """Set initial logical render size before the first window is created."""
    global _scaled_logical_size
    target = _normalize_window_size(size)
    _scaled_logical_size = target


def nudge_window_scale(
    multiplier: float, *, game_data: "GameData | None" = None
) -> surface.Surface:
    """Scale the window relative to the current zoom level."""
    delta = 1.0 if multiplier >= 1.0 else -1.0
    target_scale = current_window_scale + delta
    return apply_window_scale(target_scale, game_data=game_data)


def nudge_menu_window_scale(
    multiplier: float, *, game_data: "GameData | None" = None
) -> surface.Surface:
    """Scale the window and update menu logical size consistently."""
    delta = 1.0 if multiplier >= 1.0 else -1.0
    target_scale = current_window_scale + delta
    set_scaled_logical_size(
        (SCREEN_WIDTH, SCREEN_HEIGHT), preserve_window_size=False, game_data=game_data
    )
    return apply_window_scale(target_scale, game_data=game_data)


def toggle_fullscreen(*, game_data: "GameData | None" = None) -> surface.Surface | None:
    """Toggle fullscreen without persisting the setting."""
    global current_maximized, last_window_scale, last_window_position
    if current_maximized:
        current_maximized = False
        window_width = max(1, int(SCREEN_WIDTH * last_window_scale))
        window_height = max(1, int(SCREEN_HEIGHT * last_window_scale))
        _set_sdl2_fullscreen(False, None)
        flags = pygame.RESIZABLE
        if _use_scaled_display():
            flags |= pygame.SCALED
            window = _set_mode(_scaled_logical_size, flags)
            _set_window_size((window_width, window_height))
        else:
            window = _set_mode((window_width, window_height), flags)
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
            flags = pygame.FULLSCREEN
            render_size = (0, 0)
            if _use_scaled_display():
                flags |= pygame.SCALED
                render_size = _scaled_logical_size
            if display_index is None:
                window = _set_mode(render_size, flags)
            else:
                window = _set_mode(render_size, flags, display=display_index)
        window_width, window_height = _fetch_window_size(window)
        _update_window_caption()
        _update_window_size((window_width, window_height), source="toggle_fullscreen")
    if game_data is not None:
        game_data.state.overview_created = False
    return window


def sync_window_size(
    event: pygame.event.Event, *, game_data: "GameData | None" = None
) -> None:
    """Synchronize tracked window size with SDL window events."""
    global current_window_scale, last_window_scale, _last_window_scale_apply_ms
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
    _last_window_scale_apply_ms = None
    _maybe_apply_pending_window_scale()


def set_scaled_logical_size(
    size: tuple[int, int],
    *,
    preserve_window_size: bool = True,
    game_data: "GameData | None" = None,
) -> None:
    """Update the logical render size when using pygame.SCALED."""
    global _scaled_logical_size
    if not _use_scaled_display():
        return
    target = _normalize_window_size(size)
    if target == _scaled_logical_size:
        return
    previous_window_size = _fetch_window_size(pygame.display.get_surface())
    _scaled_logical_size = target
    flags = pygame.SCALED
    if current_maximized:
        flags |= pygame.FULLSCREEN
        _set_mode(_scaled_logical_size, flags)
    else:
        flags |= pygame.RESIZABLE
        _set_mode(_scaled_logical_size, flags)
        if preserve_window_size:
            _set_window_size(previous_window_size)
    _update_window_caption()
    if game_data is not None:
        game_data.state.overview_created = False


def adjust_menu_logical_size(*, game_data: "GameData | None" = None) -> None:
    """Match menu render size to the current window scale."""
    set_scaled_logical_size((SCREEN_WIDTH, SCREEN_HEIGHT), game_data=game_data)


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


def _set_window_size(size: tuple[int, int]) -> None:
    setter = getattr(pygame.display, "set_window_size", None)
    if callable(setter):
        try:
            setter(size)
            return
        except Exception:
            pass
    try:
        from pygame import _sdl2 as sdl2  # type: ignore[import-not-found]
    except Exception:
        return
    try:
        window = sdl2.Window.from_display_module()
    except Exception:
        return
    setter = getattr(window, "set_size", None)
    if callable(setter):
        try:
            setter(size)
            return
        except Exception:
            return
    try:
        window.size = size
    except Exception:
        return


def _set_mode(
    size: tuple[int, int], flags: int, *, display: int | None = None
) -> surface.Surface:
    vsync = _VSYNC_PREFERENCE
    try:
        kwargs: dict[str, int] = {}
        if display is not None:
            kwargs["display"] = int(display)
        if vsync is None:
            return pygame.display.set_mode(size, flags, **kwargs)
        kwargs["vsync"] = int(vsync)
        return pygame.display.set_mode(size, flags, **kwargs)
    except TypeError:
        if display is None:
            return pygame.display.set_mode(size, flags)
        return pygame.display.set_mode(size, flags, display=int(display))


def _use_scaled_display() -> bool:
    return hasattr(pygame, "SCALED")


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


def _window_center_from_position(
    window: object, position: tuple[int, int]
) -> tuple[int, int]:
    x, y = position
    try:
        width, height = window.size  # type: ignore[attr-defined]
    except Exception:
        width, height = _fetch_window_size(None)
    return x + width // 2, y + height // 2


def _get_display_count(sdl2: object) -> int | None:
    candidate = getattr(sdl2, "get_num_video_displays", None)
    if candidate is None:
        candidate = getattr(
            getattr(sdl2, "video", None), "get_num_video_displays", None
        )
    if candidate is None:
        return None
    try:
        return int(candidate())
    except Exception:
        return None


def _get_display_bounds(
    sdl2: object, display_index: int
) -> tuple[int, int, int, int] | None:
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
        for attr_name in (
            "WINDOW_FULLSCREEN_DESKTOP",
            "FULLSCREEN_DESKTOP",
            "WINDOW_FULLSCREEN",
        ):
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
    _ = source
    current_window_size = size
    if size != last_logged_window_size:
        print(f"WINDOW_SIZE {size[0]}x{size[1]}")
        last_logged_window_size = size


def _update_window_caption() -> None:
    pygame.display.set_caption("Zombie Escape")


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


def _maybe_apply_pending_window_scale() -> None:
    global \
        _last_window_scale_apply_ms, \
        _pending_window_scale, \
        _pending_window_scale_game_data
    if _pending_window_scale is None or current_maximized:
        return
    now = pygame.time.get_ticks()
    if (
        _last_window_scale_apply_ms is not None
        and now - _last_window_scale_apply_ms < _WINDOW_SCALE_COOLDOWN_MS
    ):
        return
    scale = _pending_window_scale
    game_data = _pending_window_scale_game_data
    _pending_window_scale = None
    _pending_window_scale_game_data = None
    _last_window_scale_apply_ms = now
    _apply_window_scale_now(scale, game_data=game_data)
