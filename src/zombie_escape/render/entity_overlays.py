from __future__ import annotations

import math

import pygame
from pygame import surface

from ..entities_constants import ZombieKind
from ..render_assets import (
    draw_humanoid_hand,
    draw_tracker_nose,
    draw_lightning_marker,
    draw_lineformer_direction_arm,
)
from ..render_constants import ANGLE_BINS, ZOMBIE_NOSE_COLOR, ZOMBIE_OUTLINE_COLOR


def apply_zombie_kind_overlay(
    *,
    base_surface: surface.Surface,
    kind: ZombieKind,
    facing_bin: int,
    collision_radius: int,
    wall_hug_side: int,
    wall_hug_last_side_has_wall: bool,
    lineformer_target_pos: tuple[float, float] | None,
    zombie_pos: tuple[float, float],
) -> surface.Surface:
    needs_overlay = (
        kind == ZombieKind.TRACKER
        or (
            kind == ZombieKind.WALL_HUGGER
            and wall_hug_side != 0
            and wall_hug_last_side_has_wall
        )
        or kind == ZombieKind.LINEFORMER
        or kind == ZombieKind.SOLITARY
    )
    if not needs_overlay:
        return base_surface

    image = base_surface.copy()
    angle_rad = (facing_bin % ANGLE_BINS) * (math.tau / ANGLE_BINS)
    if kind == ZombieKind.TRACKER:
        draw_tracker_nose(
            image,
            radius=collision_radius,
            angle_rad=angle_rad,
            color=ZOMBIE_NOSE_COLOR,
        )
    if (
        kind == ZombieKind.WALL_HUGGER
        and wall_hug_side != 0
        and wall_hug_last_side_has_wall
    ):
        side_sign = 1.0 if wall_hug_side > 0 else -1.0
        hand_angle = angle_rad + side_sign * (math.pi / 2.0)
        draw_humanoid_hand(
            image,
            radius=collision_radius,
            angle_rad=hand_angle,
            color=ZOMBIE_NOSE_COLOR,
        )
    if kind == ZombieKind.LINEFORMER:
        target_angle = angle_rad
        if lineformer_target_pos is not None:
            target_dx = lineformer_target_pos[0] - zombie_pos[0]
            target_dy = lineformer_target_pos[1] - zombie_pos[1]
            target_angle = math.atan2(target_dy, target_dx)
        draw_lineformer_direction_arm(
            image,
            radius=int(collision_radius),
            angle_rad=target_angle,
            color=ZOMBIE_OUTLINE_COLOR,
        )
    if kind == ZombieKind.SOLITARY:
        center_x, center_y = image.get_rect().center
        ring_radius = max(2, int(collision_radius * 1.4))
        diamond_points: list[tuple[float, float]] = [
            (center_x, center_y - ring_radius),
            (center_x + ring_radius, center_y),
            (center_x, center_y + ring_radius),
            (center_x - ring_radius, center_y),
        ]
        corner_ratio = 0.15
        for idx, vertex in enumerate(diamond_points):
            prev_vertex = diamond_points[(idx - 1) % 4]
            next_vertex = diamond_points[(idx + 1) % 4]
            prev_point = (
                vertex[0] + (prev_vertex[0] - vertex[0]) * corner_ratio,
                vertex[1] + (prev_vertex[1] - vertex[1]) * corner_ratio,
            )
            next_point = (
                vertex[0] + (next_vertex[0] - vertex[0]) * corner_ratio,
                vertex[1] + (next_vertex[1] - vertex[1]) * corner_ratio,
            )
            pygame.draw.line(
                image,
                ZOMBIE_OUTLINE_COLOR,
                (int(round(vertex[0])), int(round(vertex[1]))),
                (int(round(prev_point[0])), int(round(prev_point[1]))),
                width=1,
            )
            pygame.draw.line(
                image,
                ZOMBIE_OUTLINE_COLOR,
                (int(round(vertex[0])), int(round(vertex[1]))),
                (int(round(next_point[0])), int(round(next_point[1]))),
                width=1,
            )

    return image


def draw_paralyze_marker_overlay(
    *,
    surface_out: surface.Surface,
    now_ms: int,
    blink_ms: int,
    center: tuple[int, int],
    size: int,
    color: tuple[int, int, int],
    offset: int,
    width: int = 2,
) -> None:
    """Draw a blinking lightning marker that alternates by blink interval."""
    if blink_ms <= 0:
        return
    blink_on = (now_ms // blink_ms) % 2 == 0
    if blink_on:
        pos = (center[0] - offset, center[1] - offset)
    else:
        pos = (center[0] + offset, center[1] + offset)
    draw_lightning_marker(
        surface_out,
        center=pos,
        size=size,
        color=color,
        width=width,
    )
