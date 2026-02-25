from __future__ import annotations

import pygame

from ..entities_constants import CARRIER_BOT_HEIGHT, CARRIER_BOT_WIDTH
from ..render_constants import SPIKY_PLANT_BODY_COLOR, SPIKY_PLANT_SPIKE_COLOR
from ..render_constants import (
    PATROL_BOT_ARROW_COLOR,
    PATROL_BOT_BODY_COLOR,
    PATROL_BOT_OUTLINE_COLOR,
)
from .characters import (
    build_patrol_bot_directional_surfaces,
    build_player_directional_surfaces,
    build_survivor_directional_surfaces,
    build_zombie_directional_surfaces,
    build_zombie_dog_directional_surfaces,
)
from .items import (
    build_empty_fuel_can_surface,
    build_fuel_can_surface,
    build_shoes_surface,
)
from .vehicle import paint_car_surface, resolve_car_color


def _build_carrier_bot_icon_surface(icon_size: int) -> pygame.Surface:
    width = max(1, int(round(icon_size * (CARRIER_BOT_WIDTH / 20.0))))
    height = max(1, int(round(icon_size * (CARRIER_BOT_HEIGHT / 20.0))))
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    rect = surface.get_rect()
    pygame.draw.rect(surface, PATROL_BOT_BODY_COLOR, rect)
    pygame.draw.rect(surface, PATROL_BOT_OUTLINE_COLOR, rect, width=max(1, icon_size // 9))
    # Keep the silhouette consistent with in-game carrier bots.
    surface.set_at((rect.left, rect.top), (0, 0, 0, 0))
    surface.set_at((rect.right - 1, rect.top), (0, 0, 0, 0))
    surface.set_at((rect.left, rect.bottom - 1), (0, 0, 0, 0))
    surface.set_at((rect.right - 1, rect.bottom - 1), (0, 0, 0, 0))

    cy = rect.height // 2
    tri_w = max(2, rect.width // 4)
    tri_h = max(4, int(round(rect.height * 0.5)))
    tip_x = rect.right - max(2, rect.width // 5)
    base_x = max(rect.left + 2, tip_x - tri_w)
    right_triangle = [
        (tip_x, cy),
        (base_x, cy - tri_h // 2),
        (base_x, cy + tri_h // 2),
    ]
    pygame.draw.polygon(surface, PATROL_BOT_ARROW_COLOR, right_triangle)
    return surface


def get_character_icon(kind: str, size: int) -> pygame.Surface:
    if kind == "player":
        return build_player_directional_surfaces(size)[0]
    if kind == "buddy":
        return build_survivor_directional_surfaces(size, is_buddy=True, draw_hands=True)[0]
    if kind == "survivor":
        return build_survivor_directional_surfaces(size, is_buddy=False, draw_hands=False)[0]
    if kind == "zombie":
        return build_zombie_directional_surfaces(size, draw_hands=False)[0]
    if kind == "zombie_dog":
        return build_zombie_dog_directional_surfaces(float(size * 2.4), float(size * 1.6))[0]
    if kind == "patrol_bot":
        icon_size = max(1, int(round(size * (11.0 / 3.0))))
        return build_patrol_bot_directional_surfaces(icon_size)[0]
    if kind == "carrier_bot":
        icon_size = max(1, int(round(size * (11.0 / 3.0) * 0.8)))
        return _build_carrier_bot_icon_surface(icon_size)
    if kind == "car":
        width = max(1, int(round(size * 3.0)))
        height = max(1, int(round(size * (13.0 / 3.0))))
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        paint_car_surface(
            surf,
            width=width,
            height=height,
            color=resolve_car_color(health_ratio=1.0, appearance="default"),
        )
        return surf
    if kind == "fuel_can":
        scaled_size = int(size * 3.2)
        return build_fuel_can_surface(scaled_size, scaled_size)
    if kind == "empty_fuel_can":
        scaled_size = int(size * 3.2)
        return build_empty_fuel_can_surface(scaled_size, scaled_size)
    if kind == "shoes":
        scaled_size = int(size * 3.2)
        return build_shoes_surface(scaled_size, scaled_size)

    fallback = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
    pygame.draw.circle(fallback, (128, 128, 128), (size, size), size)
    return fallback


def get_tile_icon(kind: str, size: int) -> pygame.Surface:
    scaled_size = int(size * 3.2)
    surf = pygame.Surface((scaled_size, scaled_size), pygame.SRCALPHA)
    rect = surf.get_rect()

    if kind == "pitfall":
        pygame.draw.rect(surf, (21, 20, 20), rect)
        pygame.draw.rect(surf, (110, 110, 115), (0, 0, rect.width, 2))
    elif kind == "fall_spawn":
        pygame.draw.rect(surf, (84, 48, 29), rect)
        pygame.draw.circle(surf, (180, 0, 0), rect.center, size // 2)
    elif kind == "moving_floor":
        pygame.draw.rect(surf, (90, 90, 90), rect)
        arrow_color = (130, 130, 130)
        cx, cy = rect.center
        half_h = max(2, rect.height // 4)
        left_x = max(1, cx - (rect.width // 5))
        right_x = min(rect.right - 2, cx + (rect.width // 5))
        pygame.draw.line(
            surf,
            arrow_color,
            (left_x, cy - half_h),
            (right_x, cy),
            width=2,
        )
        pygame.draw.line(
            surf,
            arrow_color,
            (left_x, cy + half_h),
            (right_x, cy),
            width=2,
        )
    elif kind == "fire_floor":
        base = (55, 20, 18)
        diamond = (170, 36, 36)
        pygame.draw.rect(surf, base, rect)
        inset = max(1, int(round(rect.width * 0.22)))
        cx, cy = rect.center
        points = [
            (cx, rect.top + inset),
            (rect.right - inset, cy),
            (cx, rect.bottom - inset),
            (rect.left + inset, cy),
        ]
        pygame.draw.polygon(surf, diamond, points)
    elif kind == "puddle":
        ring_color = (95, 135, 185)
        ring_rect = rect.inflate(-1, -1)
        inflate_w = max(1, int(round(ring_rect.width * 0.1)))
        inflate_h = max(1, int(round(ring_rect.height * 0.1)))
        ring_rect = ring_rect.inflate(inflate_w, inflate_h)
        if ring_rect.width > 0 and ring_rect.height > 0:
            pygame.draw.ellipse(surf, ring_color, ring_rect, width=1)
    elif kind == "spiky_plant":
        center = rect.center
        body_radius = max(2, scaled_size // 4)
        pygame.draw.circle(surf, SPIKY_PLANT_BODY_COLOR, center, max(1, body_radius - 1))
        spike_inner = max(1, body_radius)
        spike_outer = max(spike_inner + 1, body_radius + 1)
        for i in range(4):
            angle = i * 90
            direction = pygame.Vector2(1, 0).rotate(angle)
            start = (
                int(center[0] + direction.x * spike_inner),
                int(center[1] + direction.y * spike_inner),
            )
            end = (
                int(center[0] + direction.x * spike_outer),
                int(center[1] + direction.y * spike_outer),
            )
            pygame.draw.line(surf, SPIKY_PLANT_SPIKE_COLOR, start, end, width=1)
    else:
        pygame.draw.rect(surf, (128, 128, 128), rect, width=1)

    return surf
