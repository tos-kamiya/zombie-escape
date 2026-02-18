from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Callable

import pygame
from pygame import surface

from ..entities_constants import INTERNAL_WALL_BEVEL_DEPTH, ZOMBIE_RADIUS
from ..models import DustRing, FallingEntity, GameData
from ..render_constants import (
    FADE_IN_DURATION_MS,
    FALLING_DUST_COLOR,
    FALLING_WHIRLWIND_COLOR,
    FALLING_ZOMBIE_COLOR,
)

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .decay_effects import DecayingEntityEffect


def _draw_fade_in_overlay(screen: surface.Surface, state: GameData | Any) -> None:
    started_at = getattr(state, "fade_in_started_at_ms", None)
    if started_at is None:
        return
    elapsed = max(0, int(state.clock.elapsed_ms) - int(started_at))
    if elapsed <= 0:
        alpha = 255
    else:
        alpha = int(255 * max(0.0, 1.0 - (elapsed / FADE_IN_DURATION_MS)))
    if alpha <= 0:
        return
    overlay = pygame.Surface(screen.get_size())
    overlay.fill((0, 0, 0))
    overlay.set_alpha(alpha)
    screen.blit(overlay, (0, 0))


def _draw_fall_whirlwind(
    screen: surface.Surface,
    apply_rect: Callable[[pygame.Rect], pygame.Rect],
    center: tuple[int, int],
    progress: float,
    *,
    scale: float = 1.0,
) -> None:
    base_alpha = FALLING_WHIRLWIND_COLOR[3]
    alpha = int(max(0, min(255, base_alpha * (1.0 - progress))))
    if alpha <= 0:
        return
    color = (
        FALLING_WHIRLWIND_COLOR[0],
        FALLING_WHIRLWIND_COLOR[1],
        FALLING_WHIRLWIND_COLOR[2],
        alpha,
    )
    safe_scale = max(0.4, scale)
    swirl_radius = max(2, int(ZOMBIE_RADIUS * 1.1 * safe_scale))
    offset = max(1, int(ZOMBIE_RADIUS * 0.6 * safe_scale))
    size = swirl_radius * 4
    swirl = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    for idx in range(2):
        angle = progress * math.tau * 0.3 + idx * (math.tau / 2)
        ox = int(math.cos(angle) * offset)
        oy = int(math.sin(angle) * offset)
        pygame.draw.circle(swirl, color, (cx + ox, cy + oy), swirl_radius, width=2)
    world_rect = pygame.Rect(0, 0, 1, 1)
    world_rect.center = center
    screen_center = apply_rect(world_rect).center
    screen.blit(swirl, swirl.get_rect(center=screen_center))


def _draw_falling_fx(
    screen: surface.Surface,
    apply_rect: Callable[[pygame.Rect], pygame.Rect],
    falling_zombies: list[FallingEntity],
    flashlight_count: int,
    dust_rings: list[DustRing],
    now_ms: int,
) -> None:
    if not falling_zombies and not dust_rings:
        return
    now = now_ms
    for fall in falling_zombies:
        pre_fx_ms = max(0, fall.pre_fx_ms)
        fall_duration_ms = max(1, fall.fall_duration_ms)
        fall_start = fall.started_at_ms + pre_fx_ms
        impact_at = fall_start + fall_duration_ms
        if now < fall_start:
            if flashlight_count > 0 and pre_fx_ms > 0:
                fx_progress = max(0.0, min(1.0, (now - fall.started_at_ms) / pre_fx_ms))
                pre_scale = 1.0 + (0.9 * fx_progress)
                _draw_fall_whirlwind(
                    screen,
                    apply_rect,
                    fall.start_pos,
                    fx_progress,
                    scale=pre_scale,
                )
            continue
        if now >= impact_at:
            continue
        fall_progress = max(0.0, min(1.0, (now - fall_start) / fall_duration_ms))

        if getattr(fall, "mode", "spawn") == "pitfall":
            scale = 1.0 - fall_progress
            scale = scale * scale
            y_offset = 0.0
        else:
            eased = 1.0 - (1.0 - fall_progress) * (1.0 - fall_progress)
            scale = 2.0 - (1.0 * eased)
            y_offset = -INTERNAL_WALL_BEVEL_DEPTH * 1.5 * (1.0 - eased)

        radius = ZOMBIE_RADIUS * scale
        cx = fall.target_pos[0]
        cy = fall.target_pos[1] + ZOMBIE_RADIUS - radius + y_offset

        world_rect = pygame.Rect(0, 0, radius * 2, radius * 2)
        world_rect.center = (int(cx), int(cy))
        screen_rect = apply_rect(world_rect)
        pygame.draw.circle(
            screen,
            FALLING_ZOMBIE_COLOR,
            screen_rect.center,
            max(1, int(screen_rect.width / 2)),
        )

    for ring in list(dust_rings):
        elapsed = now - ring.started_at_ms
        if elapsed >= ring.duration_ms:
            dust_rings.remove(ring)
            continue
        progress = max(0.0, min(1.0, elapsed / ring.duration_ms))
        alpha = int(max(0, min(255, FALLING_DUST_COLOR[3] * (1.0 - progress))))
        if alpha <= 0:
            continue
        radius = int(ZOMBIE_RADIUS * (0.7 + progress * 1.9))
        color = (
            FALLING_DUST_COLOR[0],
            FALLING_DUST_COLOR[1],
            FALLING_DUST_COLOR[2],
            alpha,
        )
        world_rect = pygame.Rect(0, 0, 1, 1)
        world_rect.center = ring.pos
        screen_center = apply_rect(world_rect).center
        pygame.draw.circle(screen, color, screen_center, radius, width=2)


def _draw_decay_fx(
    screen: surface.Surface,
    apply_rect: Callable[[pygame.Rect], pygame.Rect],
    decay_effects: list["DecayingEntityEffect"],
) -> None:
    if not decay_effects:
        return
    for effect in decay_effects:
        draw_surface = effect.build_draw_surface()
        screen.blit(draw_surface, apply_rect(effect.rect))
