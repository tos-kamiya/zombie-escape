"""Level layout constants."""

from __future__ import annotations

DEFAULT_GRID_COLS = 48
DEFAULT_GRID_ROWS = 30
DEFAULT_TILE_SIZE = 50  # world units per cell; adjust to scale the whole map
DEFAULT_WALL_LINES = 80  # reduced density (roughly 1/5 of previous 450)
DEFAULT_GRID_WIRE_WALL_LINES = int(DEFAULT_WALL_LINES * 0.7)
DEFAULT_SPARSE_WALL_DENSITY = 0.10
DEFAULT_STEEL_BEAM_CHANCE = 0.02

__all__ = [
    "DEFAULT_GRID_COLS",
    "DEFAULT_GRID_ROWS",
    "DEFAULT_TILE_SIZE",
    "DEFAULT_WALL_LINES",
    "DEFAULT_GRID_WIRE_WALL_LINES",
    "DEFAULT_SPARSE_WALL_DENSITY",
    "DEFAULT_STEEL_BEAM_CHANCE",
]
