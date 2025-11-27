from __future__ import annotations

from typing import Tuple

# Basic palette
WHITE: Tuple[int, int, int] = (255, 255, 255)
BLACK: Tuple[int, int, int] = (0, 0, 0)
RED: Tuple[int, int, int] = (255, 0, 0)
GREEN: Tuple[int, int, int] = (0, 255, 0)
BLUE: Tuple[int, int, int] = (0, 0, 255)
GRAY: Tuple[int, int, int] = (100, 100, 100)
LIGHT_GRAY: Tuple[int, int, int] = (200, 200, 200)
YELLOW: Tuple[int, int, int] = (255, 255, 0)
ORANGE: Tuple[int, int, int] = (255, 165, 0)
DARK_RED: Tuple[int, int, int] = (139, 0, 0)

# World colors
FOG_COLOR: Tuple[int, int, int, int] = (0, 0, 0, 255)
INTERNAL_WALL_COLOR: Tuple[int, int, int] = (99, 88, 70)
INTERNAL_WALL_BORDER_COLOR: Tuple[int, int, int] = (105, 93, 74)
OUTER_WALL_COLOR: Tuple[int, int, int] = (122, 114, 102)
OUTER_WALL_BORDER_COLOR: Tuple[int, int, int] = (120, 112, 100)
FLOOR_COLOR_PRIMARY: Tuple[int, int, int] = (41, 46, 51)
FLOOR_COLOR_SECONDARY: Tuple[int, int, int] = (48, 54, 61)
FLOOR_COLOR_OUTSIDE: Tuple[int, int, int] = (30, 45, 30)
FOOTPRINT_COLOR: Tuple[int, int, int] = (110, 200, 255)
STEEL_BEAM_COLOR: Tuple[int, int, int] = (110, 50, 50)
STEEL_BEAM_LINE_COLOR: Tuple[int, int, int] = (180, 90, 90)
