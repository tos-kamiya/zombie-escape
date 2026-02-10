from __future__ import annotations

from typing import Any

import pygame

from .constants import FOOTPRINT_MAX, FOOTPRINT_STEP_DISTANCE
from ..models import Footprint, GameData


def get_shrunk_sprite(
    sprite_obj: pygame.sprite.Sprite, scale_x: float, *, scale_y: float | None = None
) -> pygame.sprite.Sprite:
    if scale_y is None:
        scale_y = scale_x

    original_rect = sprite_obj.rect
    shrunk_width = int(original_rect.width * scale_x)
    shrunk_height = int(original_rect.height * scale_y)

    shrunk_width = max(1, shrunk_width)
    shrunk_height = max(1, shrunk_height)

    rect = pygame.Rect(0, 0, shrunk_width, shrunk_height)
    rect.center = original_rect.center

    new_sprite = pygame.sprite.Sprite()
    new_sprite.rect = rect
    if hasattr(sprite_obj, "radius"):
        base_radius = getattr(sprite_obj, "radius", None)
        if base_radius is not None:
            new_sprite.radius = base_radius * min(scale_x, scale_y)

    return new_sprite


def update_footprints(game_data: GameData, config: dict[str, Any]) -> None:
    """Record player steps and clean up old footprints."""
    _ = config  # Footprints are always tracked; config only affects rendering.
    state = game_data.state
    player = game_data.player
    assert player is not None

    now = state.elapsed_play_ms

    footprints = state.footprints
    if not player.in_car:
        last_pos = state.last_footprint_pos
        step_distance = FOOTPRINT_STEP_DISTANCE * 0.5
        step_distance_sq = step_distance * step_distance
        dist_sq = (
            (player.x - last_pos[0]) ** 2 + (player.y - last_pos[1]) ** 2
            if last_pos
            else None
        )
        if last_pos is None or (dist_sq is not None and dist_sq >= step_distance_sq):
            pos = (int(player.x), int(player.y))
            footprints.append(
                Footprint(pos=pos, time=now, visible=state.footprint_visible_toggle)
            )
            state.footprint_visible_toggle = not state.footprint_visible_toggle
            state.last_footprint_pos = pos

    if len(footprints) > FOOTPRINT_MAX:
        footprints = footprints[-FOOTPRINT_MAX:]

    state.footprints = footprints
