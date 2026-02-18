from __future__ import annotations

import math
from typing import Any, Callable

import pygame
from pygame import surface

from ..colors import FOOTPRINT_COLOR
from ..entities_constants import INTERNAL_WALL_BEVEL_DEPTH, MOVING_FLOOR_SPEED
from ..entities_constants import MovingFloorDirection
from ..models import Footprint
from ..render_assets import RenderAssets
from ..render_constants import (
    MOVING_FLOOR_BORDER_COLOR,
    MOVING_FLOOR_LINE_COLOR,
    MOVING_FLOOR_TILE_COLOR,
    PITFALL_ABYSS_COLOR,
    PITFALL_EDGE_DEPTH_OFFSET,
    PITFALL_EDGE_METAL_COLOR,
    PITFALL_EDGE_STRIPE_COLOR,
    PITFALL_EDGE_STRIPE_SPACING,
)
from ..screen_constants import FPS
from .puddle import draw_puddle_rings, get_puddle_phase, get_puddle_wave_color

ELECTRIFIED_FLOOR_ACCENT_COLOR = (216, 200, 90)
ELECTRIFIED_FLOOR_OVERLAY_ALPHA = 26
ELECTRIFIED_FLOOR_BORDER_ALPHA = 140

_PUDDLE_TILE_CACHE: dict[
    tuple[int, tuple[int, int, int], int, bool], surface.Surface
] = {}


def _build_moving_floor_pattern(
    direction: MovingFloorDirection,
    cell_size: int,
) -> surface.Surface:
    pattern_size = cell_size * 2
    surface_out = pygame.Surface((pattern_size, pattern_size), pygame.SRCALPHA)
    thickness = 2
    line_color = MOVING_FLOOR_LINE_COLOR
    inset = max(2, int(cell_size * 0.12))
    min_corner = inset
    max_corner = cell_size - inset
    mid = cell_size // 2
    chevron_span = max(3, int(cell_size * 0.12))

    def _draw_chevron(origin_x: int, origin_y: int, center: int) -> None:
        if direction is MovingFloorDirection.UP:
            apex_y = center - chevron_span
            base_y = center + chevron_span
            points = [
                (origin_x + min_corner, origin_y + base_y),
                (origin_x + mid, origin_y + apex_y),
                (origin_x + max_corner, origin_y + base_y),
            ]
        elif direction is MovingFloorDirection.DOWN:
            apex_y = center + chevron_span
            base_y = center - chevron_span
            points = [
                (origin_x + min_corner, origin_y + base_y),
                (origin_x + mid, origin_y + apex_y),
                (origin_x + max_corner, origin_y + base_y),
            ]
        elif direction is MovingFloorDirection.RIGHT:
            apex_x = center + chevron_span
            base_x = center - chevron_span
            points = [
                (origin_x + base_x, origin_y + min_corner),
                (origin_x + apex_x, origin_y + mid),
                (origin_x + base_x, origin_y + max_corner),
            ]
        else:
            apex_x = center - chevron_span
            base_x = center + chevron_span
            points = [
                (origin_x + base_x, origin_y + min_corner),
                (origin_x + apex_x, origin_y + mid),
                (origin_x + base_x, origin_y + max_corner),
            ]

        pygame.draw.lines(surface_out, line_color, False, points, thickness)

    spacing = max(6, cell_size // 2)
    if direction in (MovingFloorDirection.UP, MovingFloorDirection.DOWN):
        for y in range(-spacing, pattern_size + spacing, spacing):
            _draw_chevron(0, 0, y)
    else:
        for x in range(-spacing, pattern_size + spacing, spacing):
            _draw_chevron(0, 0, x)
    return surface_out


def _get_puddle_tile_surface(
    *,
    cell_size: int,
    base_color: tuple[int, int, int],
    phase: int,
    fall_spawn: bool,
) -> surface.Surface:
    key = (
        max(1, int(cell_size)),
        (int(base_color[0]), int(base_color[1]), int(base_color[2])),
        int(phase) % 4,
        bool(fall_spawn),
    )
    cached = _PUDDLE_TILE_CACHE.get(key)
    if cached is not None:
        return cached

    size = key[0]
    puddle_tile = pygame.Surface((size, size), pygame.SRCALPHA)
    tile_rect = puddle_tile.get_rect()

    pygame.draw.rect(puddle_tile, key[1], tile_rect)

    draw_puddle_rings(
        puddle_tile,
        rect=tile_rect,
        phase=key[2],
        color=get_puddle_wave_color(alpha=140),
        width=1,
    )

    _PUDDLE_TILE_CACHE[key] = puddle_tile
    return puddle_tile


def _draw_play_area(
    screen: surface.Surface,
    apply_rect: Callable[[pygame.Rect], pygame.Rect],
    view_world: pygame.Rect,
    assets: RenderAssets,
    palette: Any,
    field_rect: pygame.Rect,
    outside_cells: set[tuple[int, int]],
    fall_spawn_cells: set[tuple[int, int]],
    pitfall_cells: set[tuple[int, int]],
    puddle_cells: set[tuple[int, int]],
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection],
    electrified_cells: set[tuple[int, int]],
    cell_size: int,
    *,
    elapsed_ms: int,
) -> tuple[int, int, int, int, set[tuple[int, int]]]:
    grid_snap = assets.internal_wall_grid_snap
    xs, ys, xe, ye = (
        field_rect.left,
        field_rect.top,
        field_rect.right,
        field_rect.bottom,
    )
    xs //= grid_snap
    ys //= grid_snap
    xe //= grid_snap
    ye //= grid_snap

    play_area_rect = pygame.Rect(
        xs * grid_snap,
        ys * grid_snap,
        (xe - xs) * grid_snap,
        (ye - ys) * grid_snap,
    )
    play_area_screen_rect = apply_rect(play_area_rect)
    pygame.draw.rect(screen, palette.floor_primary, play_area_screen_rect)
    margin = grid_snap * 2
    view_world.inflate_ip(margin * 2, margin * 2)
    min_world_x = max(xs * grid_snap, view_world.left)
    max_world_x = min(xe * grid_snap, view_world.right)
    min_world_y = max(ys * grid_snap, view_world.top)
    max_world_y = min(ye * grid_snap, view_world.bottom)
    start_x = max(xs, int(min_world_x // grid_snap))
    end_x = min(xe, int(math.ceil(max_world_x / grid_snap)))
    start_y = max(ys, int(min_world_y // grid_snap))
    end_y = min(ye, int(math.ceil(max_world_y / grid_snap)))

    base_offset_px = (elapsed_ms / 1000.0) * MOVING_FLOOR_SPEED * FPS
    pattern_cache: dict[MovingFloorDirection, surface.Surface] = {}
    screen_rect = screen.get_rect()

    for y in range(start_y, end_y):
        for x in range(start_x, end_x):
            if (x, y) in outside_cells:
                lx, ly = (
                    x * grid_snap,
                    y * grid_snap,
                )
                r = pygame.Rect(
                    lx,
                    ly,
                    grid_snap,
                    grid_snap,
                )
                sr = apply_rect(r)
                if sr.colliderect(screen_rect):
                    pygame.draw.rect(screen, palette.outside, sr)
                continue

            direction = moving_floor_cells.get((x, y))
            if direction is not None:
                use_secondary = ((x // 2) + (y // 2)) % 2 == 0
                lx, ly = (
                    x * grid_snap,
                    y * grid_snap,
                )
                r = pygame.Rect(
                    lx,
                    ly,
                    grid_snap,
                    grid_snap,
                )
                sr = apply_rect(r)
                if sr.colliderect(screen_rect):
                    if (x, y) in fall_spawn_cells:
                        color = (
                            palette.fall_zone_secondary
                            if use_secondary
                            else palette.fall_zone_primary
                        )
                        pygame.draw.rect(screen, color, sr)
                    elif use_secondary:
                        pygame.draw.rect(screen, palette.floor_secondary, sr)
                    inset = 4
                    inner_rect = sr.inflate(-2 * inset, -2 * inset)
                    pygame.draw.rect(screen, MOVING_FLOOR_TILE_COLOR, inner_rect)
                    pattern = pattern_cache.get(direction)
                    if pattern is None:
                        pattern = _build_moving_floor_pattern(direction, grid_snap)
                        pattern_cache[direction] = pattern
                    signed_offset = (
                        base_offset_px
                        if direction
                        in (MovingFloorDirection.UP, MovingFloorDirection.LEFT)
                        else -base_offset_px
                    )
                    offset_px = int(signed_offset % grid_snap)
                    clip_prev = screen.get_clip()
                    screen.set_clip(inner_rect)
                    if direction in (
                        MovingFloorDirection.UP,
                        MovingFloorDirection.DOWN,
                    ):
                        blit_pos = (sr.left, sr.top - offset_px)
                    else:
                        blit_pos = (sr.left - offset_px, sr.top)
                    screen.blit(pattern, blit_pos)
                    screen.set_clip(clip_prev)
                    border_rect = inner_rect
                    pygame.draw.rect(
                        screen,
                        MOVING_FLOOR_BORDER_COLOR,
                        border_rect,
                        width=3,
                        border_radius=4,
                    )
                continue

            if (x, y) in pitfall_cells:
                lx, ly = (
                    x * grid_snap,
                    y * grid_snap,
                )
                r = pygame.Rect(
                    lx,
                    ly,
                    grid_snap,
                    grid_snap,
                )
                sr = apply_rect(r)
                if not sr.colliderect(screen_rect):
                    continue
                pygame.draw.rect(screen, PITFALL_ABYSS_COLOR, sr)

                if (x, y - 1) not in pitfall_cells:
                    edge_h = max(
                        1, INTERNAL_WALL_BEVEL_DEPTH - PITFALL_EDGE_DEPTH_OFFSET
                    )
                    pygame.draw.rect(
                        screen, PITFALL_EDGE_METAL_COLOR, (sr.x, sr.y, sr.w, edge_h)
                    )
                    for sx in range(
                        sr.x - edge_h, sr.right, PITFALL_EDGE_STRIPE_SPACING
                    ):
                        pygame.draw.line(
                            screen,
                            PITFALL_EDGE_STRIPE_COLOR,
                            (max(sr.x, sx), sr.y),
                            (min(sr.right - 1, sx + edge_h), sr.y + edge_h - 1),
                            width=2,
                        )

                continue

            use_secondary = ((x // 2) + (y // 2)) % 2 == 0
            if (x, y) in fall_spawn_cells:
                base_color = (
                    palette.fall_zone_secondary
                    if use_secondary
                    else palette.fall_zone_primary
                )
            elif use_secondary:
                base_color = palette.floor_secondary
            else:
                base_color = palette.floor_primary

            if (x, y) in puddle_cells:
                lx, ly = (
                    x * grid_snap,
                    y * grid_snap,
                )
                r = pygame.Rect(
                    lx,
                    ly,
                    grid_snap,
                    grid_snap,
                )
                sr = apply_rect(r)
                if sr.colliderect(screen_rect):
                    puddle_tile = _get_puddle_tile_surface(
                        cell_size=grid_snap,
                        base_color=base_color,
                        phase=get_puddle_phase(elapsed_ms, x, y, cycle_ms=400),
                        fall_spawn=((x, y) in fall_spawn_cells),
                    )
                    screen.blit(puddle_tile, sr.topleft)
                continue

            if (x, y) in fall_spawn_cells:
                color = (
                    palette.fall_zone_secondary
                    if use_secondary
                    else palette.fall_zone_primary
                )
            elif not use_secondary:
                continue
            else:
                color = palette.floor_secondary
            lx, ly = (
                x * grid_snap,
                y * grid_snap,
            )
            r = pygame.Rect(
                lx,
                ly,
                grid_snap,
                grid_snap,
            )
            sr = apply_rect(r)
            if sr.colliderect(screen_rect):
                pygame.draw.rect(screen, color, sr)

    if cell_size > 0 and electrified_cells:
        for cell_x, cell_y in electrified_cells:
            world_rect = pygame.Rect(
                cell_x * cell_size,
                cell_y * cell_size,
                cell_size,
                cell_size,
            )
            sr = apply_rect(world_rect)
            if sr.colliderect(screen_rect):
                inner_rect = sr.inflate(-2, -2)
                if inner_rect.width > 0 and inner_rect.height > 0:
                    overlay = pygame.Surface(
                        (inner_rect.width, inner_rect.height), pygame.SRCALPHA
                    )
                    overlay.fill(
                        (
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[0],
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[1],
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[2],
                            ELECTRIFIED_FLOOR_OVERLAY_ALPHA,
                        )
                    )
                    screen.blit(overlay, inner_rect.topleft)
                if sr.width > 0 and sr.height > 0:
                    border_surface = pygame.Surface(
                        (sr.width, sr.height), pygame.SRCALPHA
                    )
                    pygame.draw.rect(
                        border_surface,
                        (
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[0],
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[1],
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[2],
                            ELECTRIFIED_FLOOR_BORDER_ALPHA,
                        ),
                        border_surface.get_rect(),
                        width=1,
                    )
                    screen.blit(border_surface, sr.topleft)

    return xs, ys, xe, ye, outside_cells


def _draw_footprints(
    screen: surface.Surface,
    apply_rect: Callable[[pygame.Rect], pygame.Rect],
    assets: RenderAssets,
    footprints: list[Footprint],
    *,
    config: dict[str, Any],
    now_ms: int,
) -> None:
    if not config.get("footprints", {}).get("enabled", True):
        return
    now = now_ms
    for fp in footprints:
        if not fp.visible:
            continue
        age = now - fp.time
        fade = 1 - (age / assets.footprint_lifetime_ms)
        fade = max(assets.footprint_min_fade, fade)
        color = tuple(max(0, min(255, int(c * fade))) for c in FOOTPRINT_COLOR)
        fp_rect = pygame.Rect(
            fp.pos[0] - assets.footprint_radius,
            fp.pos[1] - assets.footprint_radius,
            assets.footprint_radius * 2,
            assets.footprint_radius * 2,
        )
        sr = apply_rect(fp_rect)
        if sr.colliderect(screen.get_rect().inflate(30, 30)):
            pygame.draw.circle(screen, color, sr.center, assets.footprint_radius)
