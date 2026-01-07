"""Screen and window related constants."""

from __future__ import annotations

SCREEN_WIDTH = 400  # Base logical render width
SCREEN_HEIGHT = 300  # Base logical render height
DEFAULT_WINDOW_SCALE = 2.0  # Keep ~800x600 OS window while rendering at 400x300
WINDOW_SCALE_MIN = 1.0
WINDOW_SCALE_MAX = DEFAULT_WINDOW_SCALE * 2  # Allow up to 1600x1200 windows
FPS = 60
STATUS_BAR_HEIGHT = 18

__all__ = [
    "SCREEN_WIDTH",
    "SCREEN_HEIGHT",
    "DEFAULT_WINDOW_SCALE",
    "WINDOW_SCALE_MIN",
    "WINDOW_SCALE_MAX",
    "FPS",
    "STATUS_BAR_HEIGHT",
]
