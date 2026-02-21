from __future__ import annotations

import math

import pygame

from ..colors import BLUE
from ..render_constants import (
    ANGLE_BINS,
    BUDDY_COLOR,
    HAND_SPREAD_RAD,
    HUMANOID_OUTLINE_COLOR,
    HUMANOID_OUTLINE_WIDTH,
    PATROL_BOT_ARROW_COLOR,
    PATROL_BOT_BODY_COLOR,
    PATROL_BOT_OUTLINE_COLOR,
    SURVIVOR_COLOR,
    TRAPPED_OUTLINE_COLOR,
    ZOMBIE_BODY_COLOR,
    ZOMBIE_OUTLINE_COLOR,
)
from .common import ANGLE_STEP, brighten_color

_PLAYER_UPSCALE_FACTOR = 4
_HUMANOID_SURFACE_EXTENT_RATIO = 2.0

_PLAYER_DIRECTIONAL_CACHE: dict[tuple[int, int], list[pygame.Surface]] = {}
_SURVIVOR_DIRECTIONAL_CACHE: dict[tuple[int, bool, bool, int], list[pygame.Surface]] = {}
_ZOMBIE_DIRECTIONAL_CACHE: dict[tuple[int, bool, int], list[pygame.Surface]] = {}
_ZOMBIE_DOG_DIRECTIONAL_CACHE: dict[tuple[float, float, int], list[pygame.Surface]] = {}
_PATROL_BOT_DIRECTIONAL_CACHE: dict[tuple[int, int], list[pygame.Surface]] = {}


def _hand_defaults(radius: int) -> tuple[int, int]:
    hand_radius = max(1, int(radius * 0.5))
    hand_distance = max(hand_radius + 1, int(radius * 1.0))
    return hand_radius, hand_distance


def _draw_capped_circle(
    surface: pygame.Surface,
    center: tuple[int, int],
    radius: int,
    base_color: tuple[int, int, int],
    cap_color: tuple[int, int, int],
    outline_color: tuple[int, int, int],
    outline_width: int,
    *,
    angle_rad: float = 0.0,
    hand_spread_rad: float = HAND_SPREAD_RAD,
    hand_radius: int | None = None,
    hand_distance: int | None = None,
    draw_hands: bool = True,
) -> None:
    if hand_radius is None or hand_distance is None:
        hand_radius, hand_distance = _hand_defaults(radius)
    if draw_hands:
        for direction in (-1, 1):
            hand_angle = angle_rad + (hand_spread_rad * direction)
            hand_x = int(round(center[0] + math.cos(hand_angle) * hand_distance))
            hand_y = int(round(center[1] + math.sin(hand_angle) * hand_distance))
            pygame.draw.circle(surface, base_color, (hand_x, hand_y), hand_radius)
    pygame.draw.circle(surface, cap_color, center, radius)
    if outline_width > 0:
        pygame.draw.circle(surface, outline_color, center, radius, width=outline_width)


def _build_capped_surface(
    radius: int,
    base_color: tuple[int, int, int],
    cap_color: tuple[int, int, int],
    angle_bin: int,
    *,
    outline_scale: int = 1,
    draw_hands: bool = True,
    outline_color: tuple[int, int, int] = HUMANOID_OUTLINE_COLOR,
) -> pygame.Surface:
    hand_radius, hand_distance = _hand_defaults(radius)
    max_extent = max(radius, int(round(radius * _HUMANOID_SURFACE_EXTENT_RATIO)))
    size = max_extent * 2 + 2
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    center = (max_extent + 1, max_extent + 1)
    angle_rad = (angle_bin % ANGLE_BINS) * ANGLE_STEP
    _draw_capped_circle(
        surface,
        center,
        radius,
        base_color,
        cap_color,
        outline_color,
        HUMANOID_OUTLINE_WIDTH * outline_scale,
        angle_rad=angle_rad,
        hand_radius=hand_radius,
        hand_distance=hand_distance,
        draw_hands=draw_hands,
    )
    return surface


def _build_humanoid_directional_surfaces(
    radius: int,
    *,
    base_color: tuple[int, int, int],
    cap_color: tuple[int, int, int],
    bins: int = ANGLE_BINS,
    draw_hands: bool = True,
    outline_color: tuple[int, int, int],
) -> list[pygame.Surface]:
    base_radius = radius * _PLAYER_UPSCALE_FACTOR
    base_surface = _build_capped_surface(
        base_radius,
        base_color,
        cap_color,
        0,
        outline_scale=_PLAYER_UPSCALE_FACTOR,
        draw_hands=draw_hands,
        outline_color=outline_color,
    )
    target_surface = _build_capped_surface(
        radius,
        base_color,
        cap_color,
        0,
        draw_hands=draw_hands,
        outline_color=outline_color,
    )
    target_size = target_surface.get_size()
    scale = target_size[0] / base_surface.get_width()
    half_step_deg = 360.0 / (bins * 5)
    surfaces: list[pygame.Surface] = []
    for idx in range(bins):
        rotation_deg = -(idx * 360.0 / bins - half_step_deg)
        rotated = pygame.transform.rotozoom(base_surface, rotation_deg, scale)
        framed = pygame.Surface(target_size, pygame.SRCALPHA)
        framed.blit(rotated, rotated.get_rect(center=framed.get_rect().center))
        surfaces.append(framed)
    return surfaces


def build_player_directional_surfaces(
    radius: int, *, bins: int = ANGLE_BINS
) -> list[pygame.Surface]:
    cache_key = (radius, bins)
    if cache_key in _PLAYER_DIRECTIONAL_CACHE:
        return _PLAYER_DIRECTIONAL_CACHE[cache_key]
    surfaces = _build_humanoid_directional_surfaces(
        radius,
        base_color=BLUE,
        cap_color=brighten_color(BLUE),
        bins=bins,
        outline_color=HUMANOID_OUTLINE_COLOR,
    )
    _PLAYER_DIRECTIONAL_CACHE[cache_key] = surfaces
    return surfaces


def draw_humanoid_hand(
    surface: pygame.Surface,
    *,
    radius: int,
    angle_rad: float,
    color: tuple[int, int, int],
    hand_radius: int | None = None,
    hand_distance: int | None = None,
) -> None:
    if hand_radius is None or hand_distance is None:
        hand_radius, hand_distance = _hand_defaults(radius)
    center_x, center_y = surface.get_rect().center
    hand_x = int(round(center_x + math.cos(angle_rad) * hand_distance))
    hand_y = int(round(center_y + math.sin(angle_rad) * hand_distance))
    pygame.draw.circle(surface, color, (hand_x, hand_y), hand_radius)


def draw_tracker_nose(
    surface: pygame.Surface,
    *,
    radius: int,
    angle_rad: float,
    color: tuple[int, int, int],
    length_scale: float = 0.45,
    offset_scale: float = 0.35,
) -> None:
    center_x, center_y = surface.get_rect().center
    nose_length = max(2, int(radius * length_scale))
    nose_offset = max(1, int(radius * offset_scale))
    start_x = center_x + math.cos(angle_rad) * nose_offset
    start_y = center_y + math.sin(angle_rad) * nose_offset
    end_x = center_x + math.cos(angle_rad) * (nose_offset + nose_length)
    end_y = center_y + math.sin(angle_rad) * (nose_offset + nose_length)
    pygame.draw.line(
        surface,
        color,
        (int(start_x), int(start_y)),
        (int(end_x), int(end_y)),
        width=2,
    )


def draw_lineformer_direction_arm(
    surface: pygame.Surface,
    *,
    radius: int,
    angle_rad: float,
    color: tuple[int, int, int],
) -> None:
    center_x, center_y = surface.get_rect().center
    forward_x = math.cos(angle_rad)
    forward_y = math.sin(angle_rad)
    right_x = -forward_y
    right_y = forward_x
    arc_center_offset = radius * 0.45
    arc_radius_right = max(2.0, radius * 0.8)
    arc_radius_forward = max(2.0, radius * 0.5)
    arc_forward_offset = radius * 0.8
    sweep_rad = math.radians(65)
    points: list[tuple[int, int]] = []
    for step in range(9):
        t = -sweep_rad + (2.0 * sweep_rad * step / 9.0)
        local_right = arc_radius_right * math.cos(t)
        local_forward = arc_radius_forward * math.sin(t)
        px = (
            center_x
            + right_x * (arc_center_offset + local_right)
            + forward_x * (arc_forward_offset + local_forward)
        )
        py = (
            center_y
            + right_y * (arc_center_offset + local_right)
            + forward_y * (arc_forward_offset + local_forward)
        )
        points.append((int(round(px)), int(round(py))))
    pygame.draw.lines(surface, color, False, points, width=2)


def draw_lightning_marker(
    surface: pygame.Surface,
    *,
    center: tuple[int, int],
    size: int,
    color: tuple[int, int, int],
    width: int = 2,
) -> None:
    half = max(2, int(size * 0.5))
    quarter = max(1, int(size * 0.25))
    x, y = center
    points = [
        (x - quarter, y - half),
        (x + quarter, y - quarter),
        (x - quarter, y),
        (x + quarter, y + half),
    ]
    pygame.draw.lines(surface, color, False, points, width=width)


def build_survivor_directional_surfaces(
    radius: int,
    *,
    is_buddy: bool,
    bins: int = ANGLE_BINS,
    draw_hands: bool = True,
) -> list[pygame.Surface]:
    cache_key = (radius, is_buddy, draw_hands, bins)
    if cache_key in _SURVIVOR_DIRECTIONAL_CACHE:
        return _SURVIVOR_DIRECTIONAL_CACHE[cache_key]
    fill_color = BUDDY_COLOR if is_buddy else SURVIVOR_COLOR
    surfaces = _build_humanoid_directional_surfaces(
        radius,
        base_color=fill_color,
        cap_color=brighten_color(fill_color),
        bins=bins,
        draw_hands=draw_hands,
        outline_color=HUMANOID_OUTLINE_COLOR,
    )
    _SURVIVOR_DIRECTIONAL_CACHE[cache_key] = surfaces
    return surfaces


def build_zombie_directional_surfaces(
    radius: int,
    *,
    bins: int = ANGLE_BINS,
    draw_hands: bool = True,
    is_trapped: bool = False,
) -> list[pygame.Surface]:
    cache_key = (radius, draw_hands, bins, is_trapped)
    if cache_key in _ZOMBIE_DIRECTIONAL_CACHE:
        return _ZOMBIE_DIRECTIONAL_CACHE[cache_key]

    outline_color = TRAPPED_OUTLINE_COLOR if is_trapped else ZOMBIE_OUTLINE_COLOR

    surfaces = _build_humanoid_directional_surfaces(
        radius,
        base_color=ZOMBIE_BODY_COLOR,
        cap_color=brighten_color(ZOMBIE_BODY_COLOR),
        bins=bins,
        draw_hands=draw_hands,
        outline_color=outline_color,
    )
    _ZOMBIE_DIRECTIONAL_CACHE[cache_key] = surfaces
    return surfaces


def build_zombie_dog_directional_surfaces(
    long_axis: float,
    short_axis: float,
    *,
    bins: int = ANGLE_BINS,
    is_trapped: bool = False,
) -> list[pygame.Surface]:
    cache_key = (float(long_axis), float(short_axis), bins, is_trapped)
    if cache_key in _ZOMBIE_DOG_DIRECTIONAL_CACHE:
        return _ZOMBIE_DOG_DIRECTIONAL_CACHE[cache_key]

    outline_color = TRAPPED_OUTLINE_COLOR if is_trapped else ZOMBIE_OUTLINE_COLOR
    half_long = long_axis * 0.5
    half_short = short_axis * 0.5
    width = int(math.ceil(long_axis + HUMANOID_OUTLINE_WIDTH * 2))
    height = int(math.ceil(long_axis + HUMANOID_OUTLINE_WIDTH * 2))
    center = (width / 2.0, height / 2.0)

    def _lemon_points(angle_rad: float) -> list[tuple[int, int]]:
        taper = 0.4
        waist = 0.9
        local_points = [
            (half_long, 0.0),
            (half_long * taper, half_short),
            (-half_long * taper, half_short * waist),
            (-half_long, 0.0),
            (-half_long * taper, -half_short * waist),
            (half_long * taper, -half_short),
        ]

        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        points = []

        for px, py in local_points:
            rx = px * cos_a - py * sin_a + center[0]
            ry = px * sin_a + py * cos_a + center[1]
            points.append((int(round(rx)), int(round(ry))))

        return points

    surfaces: list[pygame.Surface] = []

    for bin_idx in range(bins):
        angle_rad = bin_idx * ANGLE_STEP
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        points = _lemon_points(angle_rad)

        pygame.draw.polygon(surface, ZOMBIE_BODY_COLOR, points)

        center_x, center_y = center
        highlight_dir = (math.cos(angle_rad) * 0.25, math.sin(angle_rad) * 0.25)
        highlight_points = [
            (
                int(round((px - center_x) * 0.82 + center_x + highlight_dir[0])),
                int(round((py - center_y) * 0.82 + center_y + highlight_dir[1])),
            )
            for px, py in points
        ]

        pygame.draw.polygon(surface, brighten_color(ZOMBIE_BODY_COLOR), highlight_points)

        if HUMANOID_OUTLINE_WIDTH > 0:
            pygame.draw.polygon(
                surface,
                outline_color,
                points,
                width=HUMANOID_OUTLINE_WIDTH,
            )

        surfaces.append(surface)

    _ZOMBIE_DOG_DIRECTIONAL_CACHE[cache_key] = surfaces
    return surfaces


def _build_patrol_bot_marker_surface(
    size: int,
    marker_scale: float,
    *,
    marker_mode: str = "single",
    marker_color: tuple[int, int, int] = PATROL_BOT_ARROW_COLOR,
) -> pygame.Surface:
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    center = surface.get_rect().center
    marker_size = max(4, int(size * 0.2 * marker_scale))
    if marker_mode == "diamond":
        points = [
            (center[0], center[1] - marker_size),
            (center[0] + marker_size, center[1]),
            (center[0], center[1] + marker_size),
            (center[0] - marker_size, center[1]),
        ]
        pygame.draw.polygon(surface, marker_color, points)
    else:
        points = [
            (center[0] + marker_size, center[1]),
            (center[0], center[1] + marker_size),
            (center[0], center[1] - marker_size),
        ]
        pygame.draw.polygon(surface, marker_color, points)
    return surface


def build_patrol_bot_directional_surfaces(
    size: int,
    *,
    arrow_scale: float = 1.0,
    marker_mode: str = "single",
    bins: int = ANGLE_BINS,
) -> list[pygame.Surface]:
    cache_key = (int(size), round(float(arrow_scale), 3), marker_mode, bins)
    if cache_key in _PATROL_BOT_DIRECTIONAL_CACHE:
        return _PATROL_BOT_DIRECTIONAL_CACHE[cache_key]
    base_surface = pygame.Surface((size, size), pygame.SRCALPHA)
    center = (size // 2, size // 2)
    radius = max(1, size // 2)
    pygame.draw.circle(base_surface, PATROL_BOT_BODY_COLOR, center, radius)
    pygame.draw.circle(base_surface, PATROL_BOT_OUTLINE_COLOR, center, radius, width=2)
    if marker_mode == "diamond":
        marker_color = tuple(
            min(255, int(c * 0.7 + 255 * 0.3)) for c in PATROL_BOT_ARROW_COLOR
        )
    else:
        marker_color = PATROL_BOT_ARROW_COLOR
    marker = _build_patrol_bot_marker_surface(
        size,
        arrow_scale,
        marker_mode=marker_mode,
        marker_color=marker_color,
    )
    surfaces: list[pygame.Surface] = []
    for idx in range(bins):
        framed = base_surface.copy()
        if marker_mode == "diamond":
            framed.blit(marker, marker.get_rect(center=center))
        else:
            angle_rad = idx * ANGLE_STEP
            offset_radius = max(1.0, (size * 0.3) - (size * 0.22 * arrow_scale))
            eye_x = int(round(center[0] + math.cos(angle_rad) * offset_radius))
            eye_y = int(round(center[1] + math.sin(angle_rad) * offset_radius))
            rotated_marker = pygame.transform.rotozoom(
                marker, -math.degrees(angle_rad), 1.0
            )
            framed.blit(rotated_marker, rotated_marker.get_rect(center=(eye_x, eye_y)))
        surfaces.append(framed)
    _PATROL_BOT_DIRECTIONAL_CACHE[cache_key] = surfaces
    return surfaces
