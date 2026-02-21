from __future__ import annotations

import math
import random

import pygame

from ..colors import STEEL_BEAM_COLOR, STEEL_BEAM_LINE_COLOR, EnvironmentPalette, get_environment_palette
from ..entities_constants import INTERNAL_WALL_BEVEL_DEPTH
from .common import scale_color
from .geometry import build_beveled_polygon

_RUBBLE_SURFACE_CACHE: dict[tuple, pygame.Surface] = {}
_CRACK_STROKES_CACHE: dict[int, tuple[tuple[float, float, float, float, float], ...]] = {}
_WALL_DAMAGE_OVERLAY_CACHE: dict[
    tuple[int, int, int, int, int],
    tuple[pygame.Surface, ...],
] = {}

RUBBLE_ROTATION_DEG = 5.0
RUBBLE_OFFSET_RATIO = 0.06
RUBBLE_SCALE_RATIO = 0.9
RUBBLE_SHADOW_RATIO = 0.9


def rubble_offset_for_size(size: int) -> int:
    return max(1, int(round(size * RUBBLE_OFFSET_RATIO)))


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
        fill_min = 0.16
        fill_span = 0.84
        border_min = 0.40
        border_span = 0.60
    else:
        base_color = palette.inner_wall
        border_base_color = palette.inner_wall_border
        fill_min = 0.14
        fill_span = 0.86
        border_min = 0.42
        border_span = 0.58

    ratio = max(0.0, min(1.0, health_ratio))
    mix = fill_min + fill_span * ratio
    fill_color = (
        int(base_color[0] * mix),
        int(base_color[1] * mix),
        int(base_color[2] * mix),
    )
    border_mix = border_min + border_span * ratio
    border_color = (
        int(border_base_color[0] * border_mix),
        int(border_base_color[1] * border_mix),
        int(border_base_color[2] * border_mix),
    )
    return fill_color, border_color


def paint_wall_damage_overlay(
    surface: pygame.Surface,
    *,
    health_ratio: float,
    seed: int,
    steps: int = 12,
    circle_size_ratio: float = 0.30,
) -> None:
    clamped_health = max(0.0, min(1.0, health_ratio))
    damage_ratio = 1.0 - clamped_health
    if damage_ratio <= 0.0:
        return
    resolved_steps = max(2, int(steps))
    level = int(round(damage_ratio * (resolved_steps - 1)))
    if level <= 0:
        return

    width, height = surface.get_size()
    if width <= 0 or height <= 0:
        return
    alpha = 140
    ratio_milli = max(1, int(round(circle_size_ratio * 1000)))
    overlays = _get_wall_damage_overlays(
        width=width,
        height=height,
        seed=seed,
        steps=resolved_steps,
        alpha=alpha,
        ratio_milli=ratio_milli,
    )
    surface.blit(overlays[level], (0, 0))


def _shared_crack_strokes(seed: int) -> tuple[tuple[float, float, float, float, float], ...]:
    cached = _CRACK_STROKES_CACHE.get(seed)
    if cached is not None:
        return cached

    rng = random.Random(seed)
    strokes: list[tuple[float, float, float, float, float]] = []
    endpoints: list[tuple[float, float]] = [(0.5, 0.5)]
    target_count = 120

    def _clamp_uv(x: float, y: float) -> tuple[float, float]:
        return max(0.01, min(0.99, x)), max(0.01, min(0.99, y))

    def _edge_point() -> tuple[float, float]:
        side = rng.randrange(0, 4)
        t = rng.uniform(0.05, 0.95)
        if side == 0:
            return 0.01, t
        if side == 1:
            return 0.99, t
        if side == 2:
            return t, 0.01
        return t, 0.99

    for i in range(target_count):
        if i == 0:
            sx, sy = 0.5, 0.5
            base_angle = rng.random() * math.tau
            length = rng.uniform(0.30, 0.45)
        else:
            connect_existing = bool(endpoints) and (rng.random() < (2.0 / 3.0))
            if connect_existing:
                sx, sy = endpoints[rng.randrange(0, len(endpoints))]
                base_angle = rng.random() * math.tau
                length = rng.uniform(0.09, 0.24)
            else:
                sx, sy = _edge_point()
                to_center = math.atan2(0.5 - sy, 0.5 - sx)
                base_angle = to_center + rng.uniform(-0.55, 0.55)
                length = rng.uniform(0.10, 0.20)

        ex = sx + math.cos(base_angle) * length
        ey = sy + math.sin(base_angle) * length
        ex, ey = _clamp_uv(ex, ey)
        strength = rng.uniform(0.75, 1.0)
        strokes.append((sx, sy, ex, ey, strength))
        endpoints.append((ex, ey))

        if i > 0 and rng.random() < 0.42:
            bx_angle = base_angle + rng.uniform(-1.1, 1.1)
            bx_len = length * rng.uniform(0.38, 0.62)
            bx = sx + math.cos(bx_angle) * bx_len
            by = sy + math.sin(bx_angle) * bx_len
            bx, by = _clamp_uv(bx, by)
            b_strength = rng.uniform(0.65, 0.95)
            strokes.append((sx, sy, bx, by, b_strength))
            endpoints.append((bx, by))

    result = tuple(strokes)
    _CRACK_STROKES_CACHE[seed] = result
    return result


def _stroke_count_for_level(*, level: int, steps: int, total_strokes: int) -> int:
    if level <= 0 or steps <= 1 or total_strokes <= 0:
        return 0
    progress = level / max(1, steps - 1)
    # Make early damage marks grow more slowly while keeping late-stage density.
    eased = progress**1.35
    return max(1, min(total_strokes, int(round(total_strokes * eased))))


def _get_wall_damage_overlays(
    *,
    width: int,
    height: int,
    seed: int,
    steps: int,
    alpha: int,
    ratio_milli: int,
) -> tuple[pygame.Surface, ...]:
    cache_key = (width, height, seed, steps, ratio_milli)
    cached = _WALL_DAMAGE_OVERLAY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    empty = pygame.Surface((width, height), pygame.SRCALPHA)
    shared_strokes = _shared_crack_strokes(seed)
    if not shared_strokes:
        overlays = tuple(empty.copy() for _ in range(steps))
        _WALL_DAMAGE_OVERLAY_CACHE[cache_key] = overlays
        return overlays

    low_w = max(2, width // 2)
    low_h = max(2, height // 2)
    scale = max(0.4, ratio_milli / 300.0)
    outer_width = max(1, int(round(min(low_w, low_h) * 0.075 * scale)))
    inner_width = max(1, int(round(outer_width * 0.5)))
    total_strokes = max(6, int(round(min(len(shared_strokes), 50 * scale))))

    stroke_masks: list[pygame.Surface] = []
    for sx, sy, ex, ey, strength in shared_strokes[:total_strokes]:
        x0 = int(round(sx * (low_w - 1)))
        y0 = int(round(sy * (low_h - 1)))
        x1 = int(round(ex * (low_w - 1)))
        y1 = int(round(ey * (low_h - 1)))
        low_mask = pygame.Surface((low_w, low_h), pygame.SRCALPHA)
        outer_a = max(110, min(230, int(round(195 * strength))))
        inner_a = max(160, min(255, int(round(255 * strength))))
        pygame.draw.line(
            low_mask, (255, 255, 255, outer_a), (x0, y0), (x1, y1), outer_width
        )
        pygame.draw.line(
            low_mask, (255, 255, 255, inner_a), (x0, y0), (x1, y1), inner_width
        )
        mask = pygame.transform.scale(low_mask, (width, height))
        stroke_masks.append(mask)

    overlay_base = pygame.Surface((width, height), pygame.SRCALPHA)
    overlay_base.fill((0, 0, 0, alpha))

    coverage_mask = pygame.Surface((width, height), pygame.SRCALPHA)
    built: list[pygame.Surface] = []
    prev_count = 0
    for level in range(steps):
        target_count = _stroke_count_for_level(
            level=level, steps=steps, total_strokes=len(stroke_masks)
        )
        for mask in stroke_masks[prev_count:target_count]:
            coverage_mask.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
        prev_count = target_count
        if target_count <= 0:
            built.append(empty.copy())
            continue
        overlay = overlay_base.copy()
        overlay.blit(coverage_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        built.append(overlay)

    overlays = tuple(built)
    _WALL_DAMAGE_OVERLAY_CACHE[cache_key] = overlays
    return overlays


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
        _draw_face(top_surface, face_size=(rect_obj.width, top_height))
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

    shadow_fill = scale_color(fill_color, ratio=shadow_ratio)
    shadow_border = scale_color(border_color, ratio=shadow_ratio)
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

    shadow_rect = shadow_surface.get_rect(
        center=(center[0] + offset_px, center[1] + offset_px)
    )
    final_surface.blit(shadow_surface, shadow_rect.topleft)

    top_rect = top_surface.get_rect(center=center)
    final_surface.blit(top_surface, top_rect.topleft)

    _RUBBLE_SURFACE_CACHE[cache_key] = final_surface
    return final_surface


def resolve_steel_beam_colors(
    *,
    health_ratio: float,
    palette: EnvironmentPalette | None = None,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    _ = health_ratio, palette
    return STEEL_BEAM_COLOR, STEEL_BEAM_LINE_COLOR


def paint_steel_beam_surface(
    surface: pygame.Surface,
    *,
    base_color: tuple[int, int, int],
    line_color: tuple[int, int, int],
    health_ratio: float,
) -> None:
    surface.fill((0, 0, 0, 0))
    fill_mix = 0.25 + 0.75 * health_ratio
    fill_color = tuple(int(c * fill_mix) for c in base_color)
    rect_obj = surface.get_rect()
    side_height = max(1, int(rect_obj.height * 0.1))
    top_rect = pygame.Rect(
        rect_obj.left,
        rect_obj.top,
        rect_obj.width,
        rect_obj.height - side_height,
    )
    side_mix = 0.2 + 0.6 * health_ratio
    side_color = tuple(int(c * side_mix * 0.9) for c in base_color)
    side_rect = pygame.Rect(
        rect_obj.left,
        rect_obj.bottom - side_height,
        rect_obj.width,
        side_height,
    )
    pygame.draw.rect(surface, side_color, side_rect)
    line_mix = 0.3 + 0.7 * health_ratio
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
