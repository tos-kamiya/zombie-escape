"""Level layout constants."""

from __future__ import annotations

GRID_COLS = 48
GRID_ROWS = 30
TILE_SIZE = 50  # world units per cell; adjust to scale the whole map

CELL_SIZE = TILE_SIZE
LEVEL_WIDTH = GRID_COLS * CELL_SIZE
LEVEL_HEIGHT = GRID_ROWS * CELL_SIZE

__all__ = [
    "GRID_COLS",
    "GRID_ROWS",
    "TILE_SIZE",
    "CELL_SIZE",
    "LEVEL_WIDTH",
    "LEVEL_HEIGHT",
]
