from __future__ import annotations

from ..colors import (
    DAWN_AMBIENT_PALETTE_KEY,
    ambient_palette_key_for_flashlights,
    get_environment_palette,
)
from ..models import GameData


def _set_ambient_palette(
    game_data: GameData, key: str, *, force: bool = False
) -> None:
    """Apply a named ambient palette to all walls in the level."""

    palette = get_environment_palette(key)
    state = game_data.state
    if not force and state.ambient_palette_key == key:
        return

    state.ambient_palette_key = key
    _apply_palette_to_walls(game_data, palette, force=True)


def sync_ambient_palette_with_flashlights(
    game_data: GameData, *, force: bool = False
) -> None:
    """Sync the ambient palette with the player's flashlight inventory."""

    state = game_data.state
    if state.dawn_ready:
        _set_ambient_palette(game_data, DAWN_AMBIENT_PALETTE_KEY, force=force)
        return
    key = ambient_palette_key_for_flashlights(state.flashlight_count)
    _set_ambient_palette(game_data, key, force=force)


def _apply_palette_to_walls(
    game_data: GameData,
    palette,
    *,
    force: bool = False,
) -> None:
    if not hasattr(game_data, "groups") or not hasattr(game_data.groups, "wall_group"):
        return
    wall_group = game_data.groups.wall_group
    for wall in wall_group:
        if not hasattr(wall, "set_palette"):
            continue
        wall.set_palette(palette, force=force)
