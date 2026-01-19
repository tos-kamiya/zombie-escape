"""Shared render asset dataclasses and helpers used by multiple modules."""

from __future__ import annotations

import math

import pygame

from .colors import (
    BLACK,
    BLUE,
    DARK_RED,
    RED,
    TRACKER_OUTLINE_COLOR,
    WALL_FOLLOWER_OUTLINE_COLOR,
    YELLOW,
    EnvironmentPalette,
    ORANGE,
    STEEL_BEAM_COLOR,
    STEEL_BEAM_LINE_COLOR,
    get_environment_palette,
)
from .render_constants import (
    BUDDY_COLOR,
    HUMANOID_OUTLINE_COLOR,
    HUMANOID_OUTLINE_WIDTH,
    SURVIVOR_COLOR,
    FogRing,
    RenderAssets,
)


def _draw_outlined_circle(
    surface: pygame.Surface,
    center: tuple[int, int],
    radius: int,
    fill_color: tuple[int, int, int],
    outline_color: tuple[int, int, int],
    outline_width: int,
) -> None:
    pygame.draw.circle(surface, fill_color, center, radius)
    if outline_width > 0:
        pygame.draw.circle(surface, outline_color, center, radius, width=outline_width)


def build_beveled_polygon(
    width: int,
    height: int,
    depth: int,
    bevels: tuple[bool, bool, bool, bool],
) -> list[tuple[int, int]]:
    d = max(0, min(depth, width // 2, height // 2))
    if d == 0 or not any(bevels):
        return [(0, 0), (width, 0), (width, height), (0, height)]

    segments = 4
    tl, tr, br, bl = bevels
    points: list[tuple[int, int]] = []

    def _add_point(x: float, y: float) -> None:
        point = (int(round(x)), int(round(y)))
        if not points or points[-1] != point:
            points.append(point)

    def _add_arc(
        center_x: float,
        center_y: float,
        radius: float,
        start_deg: float,
        end_deg: float,
        *,
        skip_first: bool = False,
        skip_last: bool = False,
    ) -> None:
        for i in range(segments + 1):
            if skip_first and i == 0:
                continue
            if skip_last and i == segments:
                continue
            t = i / segments
            angle = math.radians(start_deg + (end_deg - start_deg) * t)
            _add_point(
                center_x + radius * math.cos(angle),
                center_y + radius * math.sin(angle),
            )

    _add_point(d if tl else 0, 0)
    if tr:
        _add_point(width - d, 0)
        _add_arc(width - d, d, d, -90, 0, skip_first=True)
    else:
        _add_point(width, 0)
    if br:
        _add_point(width, height - d)
        _add_arc(width - d, height - d, d, 0, 90, skip_first=True)
    else:
        _add_point(width, height)
    if bl:
        _add_point(d, height)
        _add_arc(d, height - d, d, 90, 180, skip_first=True)
    else:
        _add_point(0, height)
    if tl:
        _add_point(0, d)
        _add_arc(d, d, d, 180, 270, skip_first=True, skip_last=True)
    return points


def resolve_wall_colors(
    *,
    health_ratio: float,
    palette_category: str,
    palette: EnvironmentPalette | None,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if palette is None:
        palette = get_environment_palette(None)
    if palette_category == "outer_wall":
        base_color = palette.outer_wall
        border_base_color = palette.outer_wall_border
    else:
        base_color = palette.inner_wall
        border_base_color = palette.inner_wall_border

    if health_ratio <= 0:
        fill_color = (40, 40, 40)
        ratio = 0.0
    else:
        ratio = max(0.0, min(1.0, health_ratio))
        mix = 0.6 + 0.4 * ratio
        fill_color = (
            int(base_color[0] * mix),
            int(base_color[1] * mix),
            int(base_color[2] * mix),
        )
    border_mix = 0.6 + 0.4 * ratio
    border_color = (
        int(border_base_color[0] * border_mix),
        int(border_base_color[1] * border_mix),
        int(border_base_color[2] * border_mix),
    )
    return fill_color, border_color


CAR_COLOR_SCHEMES: dict[str, dict[str, tuple[int, int, int]]] = {
    "default": {
        "healthy": YELLOW,
        "damaged": ORANGE,
        "critical": DARK_RED,
    },
    "disabled": {
        "healthy": (185, 185, 185),
        "damaged": (150, 150, 150),
        "critical": (110, 110, 110),
    },
}


def resolve_car_color(
    *,
    health_ratio: float,
    appearance: str,
    palette: EnvironmentPalette | None = None,
) -> tuple[int, int, int]:
    palette = CAR_COLOR_SCHEMES.get(appearance, CAR_COLOR_SCHEMES["default"])
    color = palette["healthy"]
    if health_ratio < 0.6:
        color = palette["damaged"]
    if health_ratio < 0.3:
        color = palette["critical"]
    return color


def resolve_steel_beam_colors(
    *,
    health_ratio: float,
    palette: EnvironmentPalette | None = None,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    return STEEL_BEAM_COLOR, STEEL_BEAM_LINE_COLOR


def build_player_surface(radius: int) -> pygame.Surface:
    surface = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
    _draw_outlined_circle(
        surface,
        (radius + 1, radius + 1),
        radius,
        BLUE,
        HUMANOID_OUTLINE_COLOR,
        HUMANOID_OUTLINE_WIDTH,
    )
    return surface


def build_survivor_surface(radius: int, *, is_buddy: bool) -> pygame.Surface:
    surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    fill_color = BUDDY_COLOR if is_buddy else SURVIVOR_COLOR
    _draw_outlined_circle(
        surface,
        (radius, radius),
        radius,
        fill_color,
        HUMANOID_OUTLINE_COLOR,
        HUMANOID_OUTLINE_WIDTH,
    )
    return surface


def build_zombie_surface(
    radius: int,
    *,
    tracker: bool = False,
    wall_follower: bool = False,
) -> pygame.Surface:
    if tracker:
        outline_color = TRACKER_OUTLINE_COLOR
    elif wall_follower:
        outline_color = WALL_FOLLOWER_OUTLINE_COLOR
    else:
        outline_color = DARK_RED
    surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    _draw_outlined_circle(
        surface,
        (radius, radius),
        radius,
        RED,
        outline_color,
        1,
    )
    return surface


def build_car_surface(width: int, height: int) -> pygame.Surface:
    return pygame.Surface((width, height), pygame.SRCALPHA)


def paint_car_surface(
    surface: pygame.Surface,
    *,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    surface.fill((0, 0, 0, 0))

    body_rect = pygame.Rect(1, 4, width - 2, height - 8)
    front_cap_height = max(8, body_rect.height // 3)
    front_cap = pygame.Rect(
        body_rect.left, body_rect.top, body_rect.width, front_cap_height
    )
    windshield_rect = pygame.Rect(
        body_rect.left + 4,
        body_rect.top + 3,
        body_rect.width - 8,
        front_cap_height - 5,
    )

    trim_color = tuple(int(c * 0.55) for c in color)
    front_cap_color = tuple(min(255, int(c * 1.08)) for c in color)
    body_color = color
    window_color = (70, 110, 150)
    wheel_color = (35, 35, 35)

    wheel_width = width // 3
    wheel_height = 6
    for y in (body_rect.top + 4, body_rect.bottom - wheel_height - 4):
        left_wheel = pygame.Rect(2, y, wheel_width, wheel_height)
        right_wheel = pygame.Rect(width - wheel_width - 2, y, wheel_width, wheel_height)
        pygame.draw.rect(surface, wheel_color, left_wheel, border_radius=3)
        pygame.draw.rect(surface, wheel_color, right_wheel, border_radius=3)

    pygame.draw.rect(surface, body_color, body_rect, border_radius=4)
    pygame.draw.rect(surface, trim_color, body_rect, width=2, border_radius=4)
    pygame.draw.rect(surface, front_cap_color, front_cap, border_radius=10)
    pygame.draw.rect(surface, trim_color, front_cap, width=2, border_radius=10)
    pygame.draw.rect(surface, window_color, windshield_rect, border_radius=4)

    headlight_color = (245, 245, 200)
    for x in (front_cap.left + 5, front_cap.right - 5):
        pygame.draw.circle(surface, headlight_color, (x, body_rect.top + 5), 2)
    grille_rect = pygame.Rect(front_cap.centerx - 6, front_cap.top + 2, 12, 6)
    pygame.draw.rect(surface, trim_color, grille_rect, border_radius=2)
    tail_light_color = (255, 80, 50)
    for x in (body_rect.left + 5, body_rect.right - 5):
        pygame.draw.rect(
            surface,
            tail_light_color,
            (x - 2, body_rect.bottom - 5, 4, 3),
            border_radius=1,
        )


def paint_wall_surface(
    surface: pygame.Surface,
    *,
    fill_color: tuple[int, int, int],
    border_color: tuple[int, int, int],
    bevel_depth: int,
    bevel_mask: tuple[bool, bool, bool, bool],
    draw_bottom_side: bool,
    bottom_side_ratio: float,
    side_shade_ratio: float,
) -> None:
    surface.fill((0, 0, 0, 0))
    rect_obj = surface.get_rect()
    side_height = 0
    if draw_bottom_side:
        side_height = max(1, int(rect_obj.height * bottom_side_ratio))

    def _draw_face(
        target: pygame.Surface,
        *,
        face_size: tuple[int, int] | None = None,
    ) -> None:
        face_width, face_height = face_size or target.get_size()
        if bevel_depth > 0 and any(bevel_mask):
            face_polygon = build_beveled_polygon(
                face_width, face_height, bevel_depth, bevel_mask
            )
            pygame.draw.polygon(target, border_color, face_polygon)
        else:
            target.fill(border_color)
        border_width = 18
        inner_rect = target.get_rect().inflate(-border_width, -border_width)
        if inner_rect.width > 0 and inner_rect.height > 0:
            inner_depth = max(0, bevel_depth - border_width)
            if inner_depth > 0 and any(bevel_mask):
                inner_polygon = build_beveled_polygon(
                    inner_rect.width, inner_rect.height, inner_depth, bevel_mask
                )
                inner_offset_polygon = [
                    (
                        int(point[0] + inner_rect.left),
                        int(point[1] + inner_rect.top),
                    )
                    for point in inner_polygon
                ]
                pygame.draw.polygon(target, fill_color, inner_offset_polygon)
            else:
                pygame.draw.rect(target, fill_color, inner_rect)

    if draw_bottom_side:
        extra_height = max(0, int(bevel_depth / 2))
        side_draw_height = min(rect_obj.height, side_height + extra_height)
        top_rect = pygame.Rect(
            rect_obj.left,
            rect_obj.top,
            rect_obj.width,
            rect_obj.height - side_height,
        )
        side_rect = pygame.Rect(
            rect_obj.left,
            rect_obj.bottom - side_draw_height,
            rect_obj.width,
            side_draw_height,
        )
        side_color = tuple(int(c * side_shade_ratio) for c in fill_color)
        side_surface = pygame.Surface(rect_obj.size, pygame.SRCALPHA)
        if bevel_depth > 0 and any(bevel_mask):
            side_polygon = build_beveled_polygon(
                rect_obj.width, rect_obj.height, bevel_depth, bevel_mask
            )
            pygame.draw.polygon(side_surface, side_color, side_polygon)
        else:
            pygame.draw.rect(side_surface, side_color, rect_obj)
        surface.blit(side_surface, side_rect.topleft, area=side_rect)

        top_height = max(0, rect_obj.height - side_height)
        top_surface = pygame.Surface((rect_obj.width, top_height), pygame.SRCALPHA)
        _draw_face(
            top_surface,
            face_size=(rect_obj.width, top_height),
        )
        if top_rect.height > 0:
            surface.blit(top_surface, top_rect.topleft, area=top_rect)
    else:
        _draw_face(surface)


def paint_steel_beam_surface(
    surface: pygame.Surface,
    *,
    base_color: tuple[int, int, int],
    line_color: tuple[int, int, int],
    health_ratio: float,
) -> None:
    surface.fill((0, 0, 0, 0))
    fill_mix = 0.55 + 0.45 * health_ratio
    fill_color = tuple(int(c * fill_mix) for c in base_color)
    rect_obj = surface.get_rect()
    side_height = max(1, int(rect_obj.height * 0.1))
    top_rect = pygame.Rect(
        rect_obj.left,
        rect_obj.top,
        rect_obj.width,
        rect_obj.height - side_height,
    )
    side_mix = 0.45 + 0.35 * health_ratio
    side_color = tuple(int(c * side_mix * 0.9) for c in base_color)
    side_rect = pygame.Rect(
        rect_obj.left,
        rect_obj.bottom - side_height,
        rect_obj.width,
        side_height,
    )
    pygame.draw.rect(surface, side_color, side_rect)
    line_mix = 0.7 + 0.3 * health_ratio
    tuned_line_color = tuple(int(c * line_mix) for c in line_color)
    top_surface = pygame.Surface(top_rect.size, pygame.SRCALPHA)
    local_rect = top_surface.get_rect()
    pygame.draw.rect(top_surface, fill_color, local_rect)
    pygame.draw.rect(top_surface, tuned_line_color, local_rect, width=6)
    pygame.draw.line(
        top_surface,
        tuned_line_color,
        local_rect.topleft,
        local_rect.bottomright,
        width=6,
    )
    pygame.draw.line(
        top_surface,
        tuned_line_color,
        local_rect.topright,
        local_rect.bottomleft,
        width=6,
    )
    surface.blit(top_surface, top_rect.topleft)


def paint_zombie_surface(
    surface: pygame.Surface,
    *,
    radius: int,
    palm_angle: float | None = None,
    tracker: bool = False,
    wall_follower: bool = False,
) -> None:
    if tracker:
        outline_color = TRACKER_OUTLINE_COLOR
    elif wall_follower:
        outline_color = WALL_FOLLOWER_OUTLINE_COLOR
    else:
        outline_color = DARK_RED
    surface.fill((0, 0, 0, 0))
    _draw_outlined_circle(
        surface,
        (radius, radius),
        radius,
        RED,
        outline_color,
        1,
    )
    if palm_angle is None:
        return
    palm_radius = max(1, radius // 3)
    palm_offset = radius - palm_radius * 0.3
    palm_x = radius + math.cos(palm_angle) * palm_offset
    palm_y = radius + math.sin(palm_angle) * palm_offset
    pygame.draw.circle(
        surface,
        outline_color,
        (int(palm_x), int(palm_y)),
        palm_radius,
    )


def build_fuel_can_surface(width: int, height: int) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)

    # Jerrycan silhouette with cut corner
    body_pts = [
        (1, 4),
        (width - 2, 4),
        (width - 2, height - 2),
        (1, height - 2),
        (1, 8),
        (4, 4),
    ]
    pygame.draw.polygon(surface, YELLOW, body_pts)
    pygame.draw.polygon(surface, BLACK, body_pts, width=2)

    cap_size = max(2, width // 4)
    cap_rect = pygame.Rect(width - cap_size - 2, 1, cap_size, 3)
    pygame.draw.rect(surface, YELLOW, cap_rect, border_radius=1)
    pygame.draw.rect(surface, BLACK, cap_rect, width=1, border_radius=1)

    # Cross brace accent
    brace_color = (240, 200, 40)
    pygame.draw.line(
        surface, brace_color, (3, height // 2), (width - 4, height // 2), width=2
    )
    pygame.draw.line(
        surface, BLACK, (3, height // 2), (width - 4, height // 2), width=1
    )
    return surface


def build_flashlight_surface(width: int, height: int) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)

    body_color = (230, 200, 70)
    trim_color = (80, 70, 40)
    head_color = (200, 180, 90)
    beam_color = (255, 240, 180, 150)

    body_rect = pygame.Rect(1, 2, width - 4, height - 4)
    head_rect = pygame.Rect(
        body_rect.right - 3, body_rect.top - 1, 4, body_rect.height + 2
    )
    beam_points = [
        (head_rect.right + 4, head_rect.centery),
        (head_rect.right + 2, head_rect.top),
        (head_rect.right + 2, head_rect.bottom),
    ]

    pygame.draw.rect(surface, body_color, body_rect, border_radius=2)
    pygame.draw.rect(surface, trim_color, body_rect, width=1, border_radius=2)
    pygame.draw.rect(surface, head_color, head_rect, border_radius=2)
    pygame.draw.rect(surface, trim_color, head_rect, width=1, border_radius=2)
    pygame.draw.polygon(surface, beam_color, beam_points)
    return surface


__all__ = [
    "EnvironmentPalette",
    "FogRing",
    "RenderAssets",
    "build_beveled_polygon",
    "resolve_wall_colors",
    "resolve_car_color",
    "resolve_steel_beam_colors",
    "CAR_COLOR_SCHEMES",
    "build_player_surface",
    "build_survivor_surface",
    "build_zombie_surface",
    "build_car_surface",
    "paint_car_surface",
    "paint_wall_surface",
    "paint_steel_beam_surface",
    "paint_zombie_surface",
    "build_fuel_can_surface",
    "build_flashlight_surface",
]
