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
from ..localization import translate as tr

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

__all__ = [
    "ScreenID",
    "ScreenTransition",
    "present",
    "apply_window_scale",
    "nudge_window_scale",
]


def present(logical_surface: surface.Surface) -> None:
    """Scale the logical surface directly to the window and flip buffers."""
    window = pygame.display.get_surface()
    if window is None:
        return
    window_size = window.get_size()
    logical_size = logical_surface.get_size()
    if window_size == logical_size:
        window.blit(logical_surface, (0, 0))
    else:
        pygame.transform.scale(logical_surface, window_size, window)
    pygame.display.flip()


def apply_window_scale(
    scale: float, *, game_data: "GameData | None" = None
) -> surface.Surface:
    """Resize the OS window; logical render surface stays constant."""
    global current_window_scale

    clamped_scale = max(WINDOW_SCALE_MIN, min(WINDOW_SCALE_MAX, scale))
    current_window_scale = clamped_scale

    window_width = max(1, int(SCREEN_WIDTH * current_window_scale))
    window_height = max(1, int(SCREEN_HEIGHT * current_window_scale))

    new_window = pygame.display.set_mode((window_width, window_height))
    pygame.display.set_caption(
        f"{tr('game.title')} v{__version__} ({window_width}x{window_height})"
    )

    if game_data is not None:
        game_data.state.overview_created = False

    return new_window


def nudge_window_scale(
    multiplier: float, *, game_data: "GameData | None" = None
) -> surface.Surface:
    """Scale the window relative to the current zoom level."""
    target_scale = current_window_scale * multiplier
    return apply_window_scale(target_scale, game_data=game_data)
