from __future__ import annotations

from dataclasses import dataclass

# Basic palette
WHITE: tuple[int, int, int] = (255, 255, 255)
BLACK: tuple[int, int, int] = (0, 0, 0)
RED: tuple[int, int, int] = (255, 0, 0)
GREEN: tuple[int, int, int] = (0, 255, 0)
BLUE: tuple[int, int, int] = (0, 0, 255)
GRAY: tuple[int, int, int] = (100, 100, 100)
LIGHT_GRAY: tuple[int, int, int] = (200, 200, 200)
YELLOW: tuple[int, int, int] = (255, 255, 0)
ORANGE: tuple[int, int, int] = (255, 165, 0)
DARK_RED: tuple[int, int, int] = (139, 0, 0)
TRACKER_OUTLINE_COLOR: tuple[int, int, int] = (170, 70, 220)
WALL_FOLLOWER_OUTLINE_COLOR: tuple[int, int, int] = (140, 140, 140)


@dataclass(frozen=True)
class EnvironmentPalette:
    """Collection of colors that define the ambient environment."""

    floor_primary: tuple[int, int, int]
    floor_secondary: tuple[int, int, int]
    fall_zone_primary: tuple[int, int, int]
    fall_zone_secondary: tuple[int, int, int]
    outside: tuple[int, int, int]
    inner_wall: tuple[int, int, int]
    inner_wall_border: tuple[int, int, int]
    outer_wall: tuple[int, int, int]
    outer_wall_border: tuple[int, int, int]


def _clamp(value: float) -> int:
    return max(0, min(255, int(value)))


def _adjust_color(
    color: tuple[int, int, int], *, brightness: float = 1.0, saturation: float = 1.0
) -> tuple[int, int, int]:
    """Return color tinted by brightness/saturation multipliers."""

    r, g, b = color
    gray = 0.2126 * r + 0.7152 * g + 0.0722 * b

    def mix(component: int) -> int:
        value = gray + (component - gray) * saturation
        value *= brightness
        return _clamp(value)

    return mix(r), mix(g), mix(b)


DEFAULT_AMBIENT_PALETTE_KEY = "default"
NO_FLASHLIGHT_PALETTE_KEY = "no_flashlight"
DAWN_AMBIENT_PALETTE_KEY = "dawn"

# Base palette used throughout gameplay (matches the previous constants).
_DEFAULT_ENVIRONMENT_PALETTE = EnvironmentPalette(
    floor_primary=(43, 57, 70),
    floor_secondary=(50, 64, 79),
    fall_zone_primary=(84, 48, 29),
    fall_zone_secondary=(94, 54, 32),
    outside=(32, 60, 40),
    inner_wall=(125, 101, 78),
    inner_wall_border=(136, 110, 85),
    outer_wall=(136, 135, 128),
    outer_wall_border=(147, 146, 138),
)

# Dark, desaturated palette that sells the "alone without a flashlight" vibe.
_GLOOM_ENVIRONMENT_PALETTE = EnvironmentPalette(
    floor_primary=_adjust_color(
        _DEFAULT_ENVIRONMENT_PALETTE.floor_primary, brightness=0.725, saturation=0.675
    ),
    floor_secondary=_adjust_color(
        _DEFAULT_ENVIRONMENT_PALETTE.floor_secondary, brightness=0.74, saturation=0.65
    ),
    fall_zone_primary=_adjust_color(
        _DEFAULT_ENVIRONMENT_PALETTE.fall_zone_primary,
        brightness=0.725,
        saturation=0.675,
    ),
    fall_zone_secondary=_adjust_color(
        _DEFAULT_ENVIRONMENT_PALETTE.fall_zone_secondary,
        brightness=0.74,
        saturation=0.65,
    ),
    outside=_adjust_color(
        _DEFAULT_ENVIRONMENT_PALETTE.outside, brightness=0.7, saturation=0.625
    ),
    inner_wall=_adjust_color(
        _DEFAULT_ENVIRONMENT_PALETTE.inner_wall, brightness=0.775, saturation=0.7
    ),
    inner_wall_border=_adjust_color(
        _DEFAULT_ENVIRONMENT_PALETTE.inner_wall_border, brightness=0.775, saturation=0.7
    ),
    outer_wall=_adjust_color(
        _DEFAULT_ENVIRONMENT_PALETTE.outer_wall, brightness=0.75, saturation=0.675
    ),
    outer_wall_border=_adjust_color(
        _DEFAULT_ENVIRONMENT_PALETTE.outer_wall_border,
        brightness=0.75,
        saturation=0.675,
    ),
)

_DAWN_ENVIRONMENT_PALETTE = EnvironmentPalette(
    floor_primary=(58, 70, 84),
    floor_secondary=(66, 78, 92),
    fall_zone_primary=(84, 39, 29),
    fall_zone_secondary=(95, 44, 33),
    outside=(118, 140, 104),
    inner_wall=(125, 101, 78),
    inner_wall_border=(136, 110, 85),
    outer_wall=(136, 135, 128),
    outer_wall_border=(147, 146, 138),
)

ENVIRONMENT_PALETTES: dict[str, EnvironmentPalette] = {
    DEFAULT_AMBIENT_PALETTE_KEY: _DEFAULT_ENVIRONMENT_PALETTE,
    NO_FLASHLIGHT_PALETTE_KEY: _GLOOM_ENVIRONMENT_PALETTE,
    DAWN_AMBIENT_PALETTE_KEY: _DAWN_ENVIRONMENT_PALETTE,
}


def get_environment_palette(key: str | None) -> EnvironmentPalette:
    """Return the color palette for the provided key (falls back to default)."""

    if not key:
        return ENVIRONMENT_PALETTES[DEFAULT_AMBIENT_PALETTE_KEY]
    return ENVIRONMENT_PALETTES.get(
        key, ENVIRONMENT_PALETTES[DEFAULT_AMBIENT_PALETTE_KEY]
    )


def ambient_palette_key_for_flashlights(count: int) -> str:
    """Return the palette key for the provided flashlight inventory count."""

    return (
        DEFAULT_AMBIENT_PALETTE_KEY if max(0, count) > 0 else NO_FLASHLIGHT_PALETTE_KEY
    )


# World colors (default palette versions preserved for backwards compatibility).
INTERNAL_WALL_COLOR: tuple[int, int, int] = _DEFAULT_ENVIRONMENT_PALETTE.inner_wall
INTERNAL_WALL_BORDER_COLOR: tuple[int, int, int] = (
    _DEFAULT_ENVIRONMENT_PALETTE.inner_wall_border
)
OUTER_WALL_COLOR: tuple[int, int, int] = _DEFAULT_ENVIRONMENT_PALETTE.outer_wall
OUTER_WALL_BORDER_COLOR: tuple[int, int, int] = (
    _DEFAULT_ENVIRONMENT_PALETTE.outer_wall_border
)
FLOOR_COLOR_PRIMARY: tuple[int, int, int] = _DEFAULT_ENVIRONMENT_PALETTE.floor_primary
FLOOR_COLOR_SECONDARY: tuple[int, int, int] = (
    _DEFAULT_ENVIRONMENT_PALETTE.floor_secondary
)
FLOOR_COLOR_OUTSIDE: tuple[int, int, int] = _DEFAULT_ENVIRONMENT_PALETTE.outside
FOOTPRINT_COLOR: tuple[int, int, int] = (110, 200, 255)
STEEL_BEAM_COLOR: tuple[int, int, int] = (110, 50, 50)
STEEL_BEAM_LINE_COLOR: tuple[int, int, int] = (180, 90, 90)
FALL_ZONE_FLOOR_PRIMARY: tuple[int, int, int] = (
    _DEFAULT_ENVIRONMENT_PALETTE.fall_zone_primary
)
FALL_ZONE_FLOOR_SECONDARY: tuple[int, int, int] = (
    _DEFAULT_ENVIRONMENT_PALETTE.fall_zone_secondary
)


__all__ = [
    "WHITE",
    "BLACK",
    "RED",
    "GREEN",
    "BLUE",
    "GRAY",
    "LIGHT_GRAY",
    "YELLOW",
    "ORANGE",
    "DARK_RED",
    "TRACKER_OUTLINE_COLOR",
    "WALL_FOLLOWER_OUTLINE_COLOR",
    "DAWN_AMBIENT_PALETTE_KEY",
    "INTERNAL_WALL_COLOR",
    "INTERNAL_WALL_BORDER_COLOR",
    "OUTER_WALL_COLOR",
    "OUTER_WALL_BORDER_COLOR",
    "FLOOR_COLOR_PRIMARY",
    "FLOOR_COLOR_SECONDARY",
    "FLOOR_COLOR_OUTSIDE",
    "FOOTPRINT_COLOR",
    "STEEL_BEAM_COLOR",
    "STEEL_BEAM_LINE_COLOR",
    "FALL_ZONE_FLOOR_PRIMARY",
    "FALL_ZONE_FLOOR_SECONDARY",
    "EnvironmentPalette",
    "DEFAULT_AMBIENT_PALETTE_KEY",
    "NO_FLASHLIGHT_PALETTE_KEY",
    "ENVIRONMENT_PALETTES",
    "get_environment_palette",
    "ambient_palette_key_for_flashlights",
]
