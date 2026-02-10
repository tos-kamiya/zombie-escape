from __future__ import annotations

from typing import Callable, Iterable

import pygame

from ..render_assets import draw_lightning_marker


def update_paralyze_from_patrol_contact(
    *,
    entity_center: tuple[float, float],
    entity_radius: float,
    patrol_bots: Iterable[pygame.sprite.Sprite],
    now_ms: int,
    paralyze_until_ms: int,
    paralyze_duration_ms: int,
    damage_counter: int,
    damage_interval_frames: int,
    damage_amount: int,
    apply_damage: Callable[[int], None] | None,
) -> tuple[bool, int, int]:
    """Return (hit, updated_until_ms, updated_damage_counter)."""
    hit = False
    ex, ey = entity_center
    for bot in patrol_bots:
        if not bot.alive():
            continue
        bx, by = bot.rect.center
        br = getattr(bot, "collision_radius", None)
        if br is None:
            br = max(bot.rect.width, bot.rect.height) / 2
        dx = ex - bx
        dy = ey - by
        hit_range = entity_radius + float(br)
        if dx * dx + dy * dy <= hit_range * hit_range:
            hit = True
            break

    if not hit:
        return False, paralyze_until_ms, damage_counter

    paralyze_until_ms = max(paralyze_until_ms, now_ms + paralyze_duration_ms)
    if damage_interval_frames > 0 and apply_damage is not None and damage_amount > 0:
        damage_counter = (damage_counter + 1) % damage_interval_frames
        if damage_counter == 0:
            apply_damage(damage_amount)
    return True, paralyze_until_ms, damage_counter


def draw_paralyze_marker(
    *,
    surface: pygame.Surface,
    now_ms: int,
    blink_ms: int,
    center: tuple[int, int],
    size: int,
    color: tuple[int, int, int],
    offset: int,
    width: int = 2,
) -> None:
    """Draw a lightning marker that alternates position by blink_ms."""
    if blink_ms <= 0:
        return
    blink_on = (now_ms // blink_ms) % 2 == 0
    if blink_on:
        pos = (center[0] - offset, center[1] - offset)
    else:
        pos = (center[0] + offset, center[1] + offset)
    draw_lightning_marker(
        surface,
        center=pos,
        size=size,
        color=color,
        width=width,
    )
