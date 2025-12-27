"""Screen framework utilities for zombie_escape.

This module defines common types that allow each screen (title, settings,
gameplay, game over, etc.) to communicate transitions in a consistent way.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


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
    payload: dict[str, Any] | None = None


__all__ = ["ScreenID", "ScreenTransition"]
