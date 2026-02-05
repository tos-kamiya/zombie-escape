"""Shared render asset dataclasses and helpers used by multiple modules."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from .colors import (
    BLACK,
    BLUE,
    DARK_RED,
    ORANGE,
    STEEL_BEAM_COLOR,
    STEEL_BEAM_LINE_COLOR,
    YELLOW,
    EnvironmentPalette,
    get_environment_palette,
)
from .entities_constants import INTERNAL_WALL_BEVEL_DEPTH
from .render_constants import (
    ANGLE_BINS,
    BUDDY_COLOR,
    HAND_SPREAD_RAD,
    HUMANOID_OUTLINE_COLOR,
    HUMANOID_OUTLINE_WIDTH,
    SURVIVOR_COLOR,
    ZOMBIE_BODY_COLOR,
    ZOMBIE_OUTLINE_COLOR,
    FogRing,
    RenderAssets,
)


def _brighten_color(color: tuple[int, int, int], *, factor: float = 1.25) -> tuple[int, int, int]:
    return tuple(min(255, int(c * factor + 0.5)) for c in color)


ANGLE_STEP = math.tau / ANGLE_BINS

_PLAYER_UPSCALE_FACTOR = 4
_CAR_UPSCALE_FACTOR = 4

_PLAYER_DIRECTIONAL_CACHE: dict[tuple[int, int], list[pygame.Surface]] = {}
_SURVIVOR_DIRECTIONAL_CACHE: dict[tuple[int, bool, bool, int], list[pygame.Surface]] = {}
_ZOMBIE_DIRECTIONAL_CACHE: dict[tuple[int, bool, int], list[pygame.Surface]] = {}
_RUBBLE_SURFACE_CACHE: dict[tuple, pygame.Surface] = {}

RUBBLE_ROTATION_DEG = 5.0
RUBBLE_OFFSET_RATIO = 0.06
RUBBLE_SCALE_RATIO = 0.9
RUBBLE_SHADOW_RATIO = 0.9


def _scale_color(color: tuple[int, int, int], *, ratio: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * ratio + 0.5))) for c in color)


def rubble_offset_for_size(size: int) -> int:
    return max(1, int(round(size * RUBBLE_OFFSET_RATIO)))


def angle_bin_from_vector(dx: float, dy: float, *, bins: int = ANGLE_BINS) -> int | None:
    if dx == 0 and dy == 0:
        return None
    angle = math.atan2(dy, dx)
    if angle < 0:
        angle += math.tau
    step = math.tau / bins
    return int(round(angle / step)) % bins


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
    max_extent = max(radius, hand_distance + hand_radius)
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


@dataclass(frozen=True)
class PolygonSpec:
    size: tuple[int, int]
    polygons: list[list[tuple[int, int]]]


FUEL_CAN_SPEC = PolygonSpec(
    size=(13, 17),
    polygons=[
        [
            (1, 1),
            (7, 1),
            (12, 6),
            (12, 16),
            (1, 16),
        ],
        [
            (10, 1),
            (12, 3),
            (9, 4),
            (7, 3),
        ],
    ],
)

FLASHLIGHT_SPEC = PolygonSpec(
    size=(12, 10),
    polygons=[
        [
            (1, 2),
            (8, 2),
            (8, 7),
            (1, 7),
        ],
        [
            (8, 1),
            (11, 1),
            (11, 8),
            (8, 8),
        ],
    ],
)

SHOES_SPEC = PolygonSpec(
    size=(14, 10),
    polygons=[
        [
            (1, 1),
            (7, 1),
            (8, 4),
            (13, 6),
            (13, 9),
            (1, 9),
        ],
    ],
)


def _scale_polygons(
    spec: PolygonSpec,
    dst_size: tuple[int, int],
) -> list[list[tuple[int, int]]]:
    src_w, src_h = spec.size
    dst_w, dst_h = dst_size
    scale_x = dst_w / max(1, src_w)
    scale_y = dst_h / max(1, src_h)
    scaled = []
    for poly in spec.polygons:
        scaled.append(
            [
                (
                    int(round(x * scale_x)),
                    int(round(y * scale_y)),
                )
                for x, y in poly
            ]
        )
    return scaled


def _draw_polygon_surface(
    width: int,
    height: int,
    spec: PolygonSpec,
) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    draw_polygons = spec.polygons
    if (width, height) != spec.size:
        draw_polygons = _scale_polygons(spec, (width, height))
    for poly in draw_polygons:
        pygame.draw.polygon(surface, YELLOW, poly)
        pygame.draw.polygon(surface, BLACK, poly, width=1)
    return surface


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


_CAR_COLOR_SCHEMES: dict[str, dict[str, tuple[int, int, int]]] = {
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
    palette = _CAR_COLOR_SCHEMES.get(appearance, _CAR_COLOR_SCHEMES["default"])
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


def build_player_directional_surfaces(radius: int, *, bins: int = ANGLE_BINS) -> list[pygame.Surface]:
    cache_key = (radius, bins)
    if cache_key in _PLAYER_DIRECTIONAL_CACHE:
        return _PLAYER_DIRECTIONAL_CACHE[cache_key]
    surfaces = _build_humanoid_directional_surfaces(
        radius,
        base_color=BLUE,
        cap_color=_brighten_color(BLUE),
        bins=bins,
        outline_color=HUMANOID_OUTLINE_COLOR,
    )
    _PLAYER_DIRECTIONAL_CACHE[cache_key] = surfaces
    return surfaces


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


def draw_humanoid_nose(
    surface: pygame.Surface,
    *,
    radius: int,
    angle_rad: float,
    color: tuple[int, int, int],
) -> None:
    center_x, center_y = surface.get_rect().center
    nose_length = max(2, int(radius * 0.45))
    nose_offset = max(1, int(radius * 0.35))
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
        cap_color=_brighten_color(fill_color),
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
) -> list[pygame.Surface]:
    cache_key = (radius, draw_hands, bins)
    if cache_key in _ZOMBIE_DIRECTIONAL_CACHE:
        return _ZOMBIE_DIRECTIONAL_CACHE[cache_key]
    surfaces = _build_humanoid_directional_surfaces(
        radius,
        base_color=ZOMBIE_BODY_COLOR,
        cap_color=_brighten_color(ZOMBIE_BODY_COLOR),
        bins=bins,
        draw_hands=draw_hands,
        outline_color=ZOMBIE_OUTLINE_COLOR,
    )
    _ZOMBIE_DIRECTIONAL_CACHE[cache_key] = surfaces
    return surfaces


def build_car_surface(width: int, height: int) -> pygame.Surface:
    return pygame.Surface((width, height), pygame.SRCALPHA)


def paint_car_surface(
    surface: pygame.Surface,
    *,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    upscale = _CAR_UPSCALE_FACTOR
    if upscale > 1:
        up_width = width * upscale
        up_height = height * upscale
        up_surface = pygame.Surface((up_width, up_height), pygame.SRCALPHA)
        _paint_car_surface_base(up_surface, width=up_width, height=up_height, color=color)
        scaled = pygame.transform.smoothscale(up_surface, (width, height))
        surface.fill((0, 0, 0, 0))
        surface.blit(scaled, (0, 0))
        return
    _paint_car_surface_base(surface, width=width, height=height, color=color)


def _paint_car_surface_base(
    surface: pygame.Surface,
    *,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    surface.fill((0, 0, 0, 0))

    trim_color = tuple(int(c * 0.6) for c in color)
    body_color = tuple(min(255, int(c * 1.15)) for c in color)
    tail_light_color = (255, 80, 50)
    headlight_color = (200, 200, 200)

    base_width = 150.0
    base_height = 210.0
    scale_x = width / base_width
    scale_y = height / base_height

    def _rect(x: float, y: float, w: float, h: float) -> pygame.Rect:
        return pygame.Rect(
            int(round(x * scale_x)),
            int(round(y * scale_y)),
            max(1, int(round(w * scale_x))),
            max(1, int(round(h * scale_y))),
        )

    def _radius(value: float) -> int:
        return max(1, int(round(value * min(scale_x, scale_y))))

    body_top = _rect(0, 0, 150, 140)
    body_bottom = _rect(0, 70, 150, 140)
    rear_bed = _rect(16, 98, 118, 88)

    pygame.draw.rect(surface, trim_color, body_top, border_radius=_radius(50))
    pygame.draw.rect(surface, trim_color, body_bottom, border_radius=_radius(37))
    pygame.draw.rect(surface, body_color, rear_bed)

    tail_left = _rect(30, 190, 30, 20)
    tail_right = _rect(90, 190, 30, 20)
    pygame.draw.rect(surface, tail_light_color, tail_left)
    pygame.draw.rect(surface, tail_light_color, tail_right)

    headlight_left = _rect(15, 7, 40, 20)
    headlight_right = _rect(95, 7, 40, 20)
    pygame.draw.ellipse(surface, headlight_color, headlight_left)
    pygame.draw.ellipse(surface, headlight_color, headlight_right)


def build_car_directional_surfaces(base_surface: pygame.Surface, *, bins: int = ANGLE_BINS) -> list[pygame.Surface]:
    """Return pre-rotated car surfaces matching angle_bin_from_vector bins."""
    surfaces: list[pygame.Surface] = []
    upscale = _CAR_UPSCALE_FACTOR
    if upscale > 1:
        src_size = base_surface.get_size()
        upscale_surface = pygame.transform.scale(
            base_surface,
            (src_size[0] * upscale, src_size[1] * upscale),
        )
    else:
        upscale_surface = base_surface
    for idx in range(bins):
        angle_rad = idx * ANGLE_STEP
        rotation_deg = -math.degrees(angle_rad) - 90
        rotated = pygame.transform.rotate(upscale_surface, rotation_deg)
        if upscale > 1:
            scaled = pygame.transform.smoothscale(
                rotated,
                (
                    max(1, rotated.get_width() // upscale),
                    max(1, rotated.get_height() // upscale),
                ),
            )
            surfaces.append(scaled)
        else:
            surfaces.append(rotated)
    return surfaces


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
            face_polygon = build_beveled_polygon(face_width, face_height, bevel_depth, bevel_mask)
            pygame.draw.polygon(target, border_color, face_polygon)
        else:
            target.fill(border_color)
        border_width = 18
        inner_rect = target.get_rect().inflate(-border_width, -border_width)
        if inner_rect.width > 0 and inner_rect.height > 0:
            inner_depth = max(0, bevel_depth - border_width)
            if inner_depth > 0 and any(bevel_mask):
                inner_polygon = build_beveled_polygon(inner_rect.width, inner_rect.height, inner_depth, bevel_mask)
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
            side_polygon = build_beveled_polygon(rect_obj.width, rect_obj.height, bevel_depth, bevel_mask)
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


def build_rubble_wall_surface(
    size: int,
    *,
    fill_color: tuple[int, int, int],
    border_color: tuple[int, int, int],
    angle_deg: float,
    offset_px: int | None = None,
    scale_ratio: float = RUBBLE_SCALE_RATIO,
    shadow_ratio: float = RUBBLE_SHADOW_RATIO,
    bevel_depth: int = INTERNAL_WALL_BEVEL_DEPTH,
) -> pygame.Surface:
    offset_px = offset_px if offset_px is not None else rubble_offset_for_size(size)
    safe_size = max(1, size)
    base_size = max(1, int(round(safe_size * scale_ratio)))
    tuned_bevel = min(bevel_depth, max(1, base_size // 2))
    cache_key = (
        safe_size,
        fill_color,
        border_color,
        angle_deg,
        offset_px,
        scale_ratio,
        shadow_ratio,
        tuned_bevel,
    )
    cached = _RUBBLE_SURFACE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    top_surface = pygame.Surface((base_size, base_size), pygame.SRCALPHA)
    paint_wall_surface(
        top_surface,
        fill_color=fill_color,
        border_color=border_color,
        bevel_depth=tuned_bevel,
        bevel_mask=(False, False, False, False),
        draw_bottom_side=False,
        bottom_side_ratio=0.1,
        side_shade_ratio=0.9,
    )

    shadow_fill = _scale_color(fill_color, ratio=shadow_ratio)
    shadow_border = _scale_color(border_color, ratio=shadow_ratio)
    shadow_surface = pygame.Surface((base_size, base_size), pygame.SRCALPHA)
    paint_wall_surface(
        shadow_surface,
        fill_color=shadow_fill,
        border_color=shadow_border,
        bevel_depth=tuned_bevel,
        bevel_mask=(False, False, False, False),
        draw_bottom_side=False,
        bottom_side_ratio=0.1,
        side_shade_ratio=0.9,
    )

    if angle_deg:
        top_surface = pygame.transform.rotate(top_surface, angle_deg)
        shadow_surface = pygame.transform.rotate(shadow_surface, angle_deg)

    final_surface = pygame.Surface((safe_size, safe_size), pygame.SRCALPHA)
    center = final_surface.get_rect().center

    shadow_rect = shadow_surface.get_rect(center=(center[0] + offset_px, center[1] + offset_px))
    final_surface.blit(shadow_surface, shadow_rect.topleft)

    top_rect = top_surface.get_rect(center=center)
    final_surface.blit(top_surface, top_rect.topleft)

    _RUBBLE_SURFACE_CACHE[cache_key] = final_surface
    return final_surface


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


def build_fuel_can_surface(width: int, height: int) -> pygame.Surface:
    return _draw_polygon_surface(width, height, FUEL_CAN_SPEC)


def build_flashlight_surface(width: int, height: int) -> pygame.Surface:
    return _draw_polygon_surface(width, height, FLASHLIGHT_SPEC)


def build_shoes_surface(width: int, height: int) -> pygame.Surface:
    return _draw_polygon_surface(width, height, SHOES_SPEC)


__all__ = [
    "angle_bin_from_vector",
    "EnvironmentPalette",
    "FogRing",
    "RenderAssets",
    "build_beveled_polygon",
    "resolve_wall_colors",
    "resolve_car_color",
    "resolve_steel_beam_colors",
    "build_player_directional_surfaces",
    "draw_humanoid_hand",
    "draw_humanoid_nose",
    "build_survivor_directional_surfaces",
    "build_zombie_directional_surfaces",
    "build_car_surface",
    "build_car_directional_surfaces",
    "paint_car_surface",
    "paint_wall_surface",
    "build_rubble_wall_surface",
    "rubble_offset_for_size",
    "RUBBLE_ROTATION_DEG",
    "paint_steel_beam_surface",
    "build_fuel_can_surface",
    "build_flashlight_surface",
    "build_shoes_surface",
]
