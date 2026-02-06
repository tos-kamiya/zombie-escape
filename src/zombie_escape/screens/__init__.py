"""Screen framework utilities for zombie_escape.

This module defines common types that allow each screen (title, settings,
gameplay, game over, etc.) to communicate transitions in a consistent way.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

try:  # pragma: no cover - version fallback not critical for tests
    from ..__about__ import __version__
except Exception:  # pragma: no cover - fallback version
    __version__ = "0.0.0-unknown"
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


__all__ = [
    "ScreenID",
    "ScreenTransition",
    "TITLE_HEADER_Y",
    "TITLE_SECTION_TOP",
]

TITLE_HEADER_Y = 20
TITLE_SECTION_TOP = 45
