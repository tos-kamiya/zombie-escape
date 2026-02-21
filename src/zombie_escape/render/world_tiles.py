from __future__ import annotations

import math
import random
from typing import Any, Callable, Iterable

import pygame
from pygame import surface

from ..colors import FOOTPRINT_COLOR
from ..entities_constants import INTERNAL_WALL_BEVEL_DEPTH, MOVING_FLOOR_SPEED
from ..entities_constants import MovingFloorDirection
from ..models import Footprint
from ..render_assets import RenderAssets
from ..render_constants import (
    FIRE_FLOOR_FLAME_COLORS,
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
from .puddle import (
    PUDDLE_MOONLIGHT_ALPHA,
    PUDDLE_MOONLIGHT_CYCLE_MS,
    draw_puddle_rings,
    get_puddle_phase,
    get_puddle_wave_color,
)

ELECTRIFIED_FLOOR_ACCENT_COLOR = (216, 200, 90)
ELECTRIFIED_FLOOR_OVERLAY_ALPHA = 26
ELECTRIFIED_FLOOR_BORDER_ALPHA = 140

_PUDDLE_TILE_CACHE: dict[tuple[int, tuple[int, int, int], int], surface.Surface] = {}
_METAL_TILE_CACHE: dict[
    tuple[
        int,
        tuple[int, int, int],
        tuple[int, int, int],
        tuple[int, int, int],
        tuple[int, int, int],
    ],
    surface.Surface,
] = {}
_FIRE_TILE_CACHE: dict[
    tuple[int, int, tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]],
    surface.Surface,
] = {}
_FLOOR_RUIN_TILE_CACHE: dict[
    tuple[int, tuple[int, int, int], tuple[int, int, int], int, int],
    surface.Surface,
] = {}
_FLOOR_BARCODE_TILE_CACHE: dict[
    tuple[int, tuple[int, int, int], int],
    surface.Surface,
] = {}

_FLOOR_RUIN_VARIANTS = 8


def build_floor_ruin_cells(
    *,
    candidate_cells: Iterable[tuple[int, int]],
    rubble_ratio: float,
) -> dict[tuple[int, int], int]:
    if rubble_ratio <= 0.0:
        return {}
    density = max(0.0, min(1.0, rubble_ratio)) * 0.15
    if density <= 0.0:
        return {}
    chosen: dict[tuple[int, int], int] = {}
    for cell in candidate_cells:
        if random.random() < density:
            chosen[cell] = random.randrange(0, _FLOOR_RUIN_VARIANTS)
    return chosen


def _floor_clutter_tier_for_cell(*, x: int, y: int, xs: int, ys: int, xe: int, ye: int) -> int:
    dist_left = x - xs
    dist_right = (xe - 1) - x
    dist_top = y - ys
    dist_bottom = (ye - 1) - y
    edge_distance = min(dist_left, dist_right, dist_top, dist_bottom)
    if edge_distance <= 1:
        return 2
    if edge_distance <= 3:
        return 1
    return 0


def _encode_stage_barcode_pattern(stage_number: int) -> str:
    value = max(0, int(stage_number))
    bits = bin(value)[2:]
    parity_bit = "0" if (bits.count("1") % 2 == 0) else "1"
    start = "**_"
    end = "_**"
    encoded_bits = "".join("_*" if bit == "0" else "*_" for bit in bits)
    encoded_parity = "_*" if parity_bit == "0" else "*_"
    return start + encoded_bits + encoded_parity + end


def _get_floor_barcode_overlay_tile(
    *,
    cell_size: int,
    base_color: tuple[int, int, int],
    stage_number: int,
) -> surface.Surface:
    key = (
        max(1, int(cell_size)),
        (int(base_color[0]), int(base_color[1]), int(base_color[2])),
        max(0, int(stage_number)),
    )
    cached = _FLOOR_BARCODE_TILE_CACHE.get(key)
    if cached is not None:
        return cached

    size = key[0]
    overlay = pygame.Surface((size, size), pygame.SRCALPHA)
    pattern = _encode_stage_barcode_pattern(key[2])
    module_width = 1
    bar_height = 2
    pattern_width = len(pattern) * module_width
    pad_x = 1
    pad_y = 1
    x0 = max(0, size - pattern_width - pad_x)
    y0 = max(0, size - bar_height - pad_y)
    alpha = 44
    color = (
        max(0, min(255, int(base_color[0] * 0.35))),
        max(0, min(255, int(base_color[1] * 0.35))),
        max(0, min(255, int(base_color[2] * 0.35))),
        alpha,
    )
    for i, symbol in enumerate(pattern):
        if symbol != "*":
            continue
        x = x0 + i * module_width
        if x >= size:
            continue
        bar_width = min(module_width, size - x)
        if bar_width <= 0:
            continue
        pygame.draw.rect(overlay, color, pygame.Rect(x, y0, bar_width, bar_height))

    _FLOOR_BARCODE_TILE_CACHE[key] = overlay
    return overlay


def _get_floor_ruin_overlay_tile(
    *,
    cell_size: int,
    base_color: tuple[int, int, int],
    wall_color: tuple[int, int, int],
    tier: int,
    variant: int,
) -> surface.Surface:
    key = (
        max(1, int(cell_size)),
        (int(base_color[0]), int(base_color[1]), int(base_color[2])),
        (int(wall_color[0]), int(wall_color[1]), int(wall_color[2])),
        int(tier),
        int(variant),
    )
    cached = _FLOOR_RUIN_TILE_CACHE.get(key)
    if cached is not None:
        return cached

    size = key[0]
    overlay = pygame.Surface((size, size), pygame.SRCALPHA)
    rng = random

    # Dust: sparse 1px noise with low alpha.
    dust_count = (2, 4, 7)[max(0, min(2, tier))]
    dark_dust = (
        max(0, base_color[0] - 28),
        max(0, base_color[1] - 28),
        max(0, base_color[2] - 28),
        34,
    )
    light_dust = (
        min(255, base_color[0] + 14),
        min(255, base_color[1] + 14),
        min(255, base_color[2] + 14),
        24,
    )
    for _ in range(dust_count):
        px = rng.randrange(0, size)
        py = rng.randrange(0, size)
        overlay.set_at((px, py), dark_dust if rng.random() < 0.7 else light_dust)

    # Debris: triangular chips using wall-like tones; more frequent near edges.
    debris_count = (1, 2, 3)[max(0, min(2, tier))]
    for _ in range(debris_count):
        cx = rng.randrange(2, max(3, size - 2))
        cy = rng.randrange(2, max(3, size - 2))
        chip_color = (
            max(0, int(wall_color[0] * rng.uniform(0.70, 0.92))),
            max(0, int(wall_color[1] * rng.uniform(0.70, 0.92))),
            max(0, int(wall_color[2] * rng.uniform(0.70, 0.92))),
            118,
        )
        # ~50% larger than previous micro chips, and intentionally irregular.
        base_angle = rng.uniform(0.0, math.tau)
        # Avoid near-equilateral spacing by using uneven angular intervals.
        angle_1 = base_angle
        angle_2 = angle_1 + rng.uniform(0.85, 2.25)
        angle_3 = angle_2 + rng.uniform(0.95, 2.55)
        radii = [
            rng.uniform(2.0, 4.3),
            rng.uniform(1.6, 4.6),
            rng.uniform(2.2, 5.0),
        ]
        points = []
        for angle, radius in zip((angle_1, angle_2, angle_3), radii):
            px = int(round(cx + math.cos(angle) * radius))
            py = int(round(cy + math.sin(angle) * radius))
            points.append((px, py))
        if len({points[0], points[1], points[2]}) < 3:
            continue
        pygame.draw.polygon(overlay, chip_color, points)

    # Screws/metal bits: metallic tiny T marks.
    screw_prob = (0.055, 0.12, 0.18)[max(0, min(2, tier))]
    screw_count = 1 if rng.random() < screw_prob else 0
    if tier >= 2 and rng.random() < 0.09:
        screw_count += 1
    for _ in range(screw_count):
        sx = rng.randrange(1, max(2, size - 1))
        sy = rng.randrange(1, max(2, size - 1))
        screw_color = (138, 146, 158, 180)
        orientation = rng.randrange(0, 4)
        if orientation == 0:  # up
            pygame.draw.line(
                overlay, screw_color, (sx - 1, sy - 1), (sx + 1, sy - 1), width=1
            )
            pygame.draw.line(overlay, screw_color, (sx, sy - 1), (sx, sy + 1), width=1)
        elif orientation == 1:  # right
            pygame.draw.line(
                overlay, screw_color, (sx + 1, sy - 1), (sx + 1, sy + 1), width=1
            )
            pygame.draw.line(overlay, screw_color, (sx - 1, sy), (sx + 1, sy), width=1)
        elif orientation == 2:  # down
            pygame.draw.line(
                overlay, screw_color, (sx - 1, sy + 1), (sx + 1, sy + 1), width=1
            )
            pygame.draw.line(overlay, screw_color, (sx, sy - 1), (sx, sy + 1), width=1)
        else:  # left
            pygame.draw.line(
                overlay, screw_color, (sx - 1, sy - 1), (sx - 1, sy + 1), width=1
            )
            pygame.draw.line(overlay, screw_color, (sx - 1, sy), (sx + 1, sy), width=1)

    _FLOOR_RUIN_TILE_CACHE[key] = overlay
    return overlay


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
) -> surface.Surface:
    key = (
        max(1, int(cell_size)),
        (int(base_color[0]), int(base_color[1]), int(base_color[2])),
        int(phase) % 12,
    )
    cached = _PUDDLE_TILE_CACHE.get(key)
    if cached is not None:
        return cached

    size = key[0]
    puddle_tile = pygame.Surface((size, size), pygame.SRCALPHA)
    tile_rect = puddle_tile.get_rect()

    pygame.draw.rect(puddle_tile, key[1], tile_rect)
    pygame.draw.rect(
        puddle_tile,
        get_puddle_wave_color(alpha=50),
        tile_rect,
        width=2,
    )

    draw_puddle_rings(
        puddle_tile,
        rect=tile_rect,
        phase=key[2],
        color=get_puddle_wave_color(alpha=PUDDLE_MOONLIGHT_ALPHA),
        width=2,
    )

    _PUDDLE_TILE_CACHE[key] = puddle_tile
    return puddle_tile


def _get_metal_tile_surface(*, cell_size: int, palette: Any) -> surface.Surface:
    key = (
        max(1, int(cell_size)),
        tuple(map(int, palette.metal_floor_base)),
        tuple(map(int, palette.metal_floor_line)),
        tuple(map(int, palette.metal_floor_highlight)),
        tuple(map(int, palette.metal_floor_hairline)),
    )
    cached = _METAL_TILE_CACHE.get(key)
    if cached is not None:
        return cached
    size = key[0]
    metal_base = key[1]
    metal_line = key[2]
    metal_highlight = key[3]
    metal_hairline = key[4]
    tile = pygame.Surface((size, size), pygame.SRCALPHA)
    tile.fill(metal_base)

    frame_color = (
        max(0, int(metal_base[0] * 0.70)),
        max(0, int(metal_base[1] * 0.70)),
        max(0, int(metal_base[2] * 0.70)),
    )
    inset = max(2, size // 8)
    panel_rect = pygame.Rect(
        inset, inset, max(1, size - inset * 2), max(1, size - inset * 2)
    )
    pygame.draw.rect(tile, frame_color, tile.get_rect(), width=max(1, size // 14))

    overlay = pygame.Surface((size, size), pygame.SRCALPHA)
    base_step = max(5, size // 4)
    rhythm = [
        base_step,
        max(3, base_step - 2),
        base_step + 1,
        max(4, base_step - 1),
    ]
    sx = panel_rect.left - panel_rect.height
    i = 0
    while sx <= panel_rect.right + panel_rect.height:
        start = (sx, panel_rect.bottom)
        end = (sx + panel_rect.height, panel_rect.top)
        pygame.draw.line(
            overlay,
            metal_highlight,
            start,
            end,
            width=max(1, size // 18),
        )
        pygame.draw.line(
            overlay,
            metal_line,
            (start[0] + 1, start[1]),
            (end[0] + 1, end[1]),
            width=1,
        )
        sx += rhythm[i % len(rhythm)]
        i += 1

    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), panel_rect)
    overlay.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    tile.blit(overlay, (0, 0))

    # Subtle top-left specular band to match reinforced-wall metallic feel.
    band = pygame.Surface((max(2, size // 3), max(2, size // 10)), pygame.SRCALPHA)
    band.fill((*metal_hairline, 44))
    tile.blit(band, (inset + 1, inset + 1))

    _METAL_TILE_CACHE[key] = tile
    return tile


def _get_fire_tile_surface(*, cell_size: int, phase: int, palette: Any) -> surface.Surface:
    key = (
        max(1, int(cell_size)),
        int(phase) % 3,
        tuple(map(int, palette.fire_floor_base)),
        tuple(map(int, palette.fire_glass_base)),
        tuple(map(int, palette.fire_grate_edge)),
    )
    cached = _FIRE_TILE_CACHE.get(key)
    if cached is not None:
        return cached
    size = key[0]
    fire_base = key[2]
    fire_glass_base = key[3]
    fire_grate_edge = key[4]
    tile = pygame.Surface((size, size), pygame.SRCALPHA)
    pulse = key[1]

    # Molten base under the grate.
    tile.fill(fire_base)
    band_h = max(3, size // 6)
    for row in range(0, size, band_h):
        color = FIRE_FLOOR_FLAME_COLORS[(row // band_h + pulse) % len(FIRE_FLOOR_FLAME_COLORS)]
        glow_rect = pygame.Rect(0, row, size, min(band_h + 1, size - row))
        pygame.draw.rect(tile, color, glow_rect)
    for idx, color in enumerate(FIRE_FLOOR_FLAME_COLORS):
        ember_w = max(2, int(size * (0.18 + idx * 0.03)))
        ember_h = max(2, int(size * (0.12 + idx * 0.02)))
        ox = (idx * (size // 3) + pulse * 2) % max(1, size - ember_w)
        oy = ((idx + pulse) * (size // 4)) % max(1, size - ember_h)
        pygame.draw.ellipse(tile, color, pygame.Rect(ox, oy, ember_w, ember_h))

    # Dark tempered-glass grate overlay.
    grate = pygame.Surface((size, size), pygame.SRCALPHA)
    grate.fill((*fire_glass_base, 232))
    slot_step = max(6, size // 4)
    diamond_r = max(2, int(slot_step // 2.5))
    row_index = 0
    for cy in range(slot_step // 2, size, slot_step):
        row_offset = (slot_step // 2) if (row_index % 2 == 1) else 0
        start_x = (slot_step // 2) - row_offset
        for cx in range(start_x, size + slot_step, slot_step):
            if cx < -diamond_r or cx > size + diamond_r:
                continue
            points = [
                (cx, cy - diamond_r),
                (cx + diamond_r, cy),
                (cx, cy + diamond_r),
                (cx - diamond_r, cy),
            ]
            pygame.draw.polygon(grate, (0, 0, 0, 0), points)
            pygame.draw.polygon(grate, (*fire_glass_base, 244), points, width=1)
        row_index += 1
    pygame.draw.rect(grate, fire_grate_edge, grate.get_rect(), width=max(1, size // 14))
    tile.blit(grate, (0, 0))

    _FIRE_TILE_CACHE[key] = tile
    return tile


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
    fire_floor_cells: set[tuple[int, int]],
    metal_floor_cells: set[tuple[int, int]],
    puddle_cells: set[tuple[int, int]],
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection],
    floor_ruin_cells: dict[tuple[int, int], int],
    electrified_cells: set[tuple[int, int]],
    cell_size: int,
    stage_number: int,
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

            if (x, y) in fire_floor_cells:
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
                    phase = ((elapsed_ms // 360) + x + y) % 3
                    fire_tile = _get_fire_tile_surface(
                        cell_size=grid_snap,
                        phase=phase,
                        palette=palette,
                    )
                    screen.blit(fire_tile, sr.topleft)
                    border_color = (
                        palette.fall_zone_primary
                        if (x, y) in fall_spawn_cells
                        else palette.floor_primary
                    )
                    pygame.draw.rect(screen, border_color, sr, width=1)
                continue

            if (x, y) in metal_floor_cells:
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
                    metal_tile = _get_metal_tile_surface(
                        cell_size=grid_snap,
                        palette=palette,
                    )
                    screen.blit(metal_tile, sr.topleft)
                    border_color = (
                        palette.fall_zone_primary
                        if (x, y) in fall_spawn_cells
                        else palette.floor_primary
                    )
                    pygame.draw.rect(screen, border_color, sr, width=1)
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
                        phase=get_puddle_phase(
                            elapsed_ms,
                            x,
                            y,
                            cycle_ms=PUDDLE_MOONLIGHT_CYCLE_MS,
                        ),
                    )
                    screen.blit(puddle_tile, sr.topleft)
                continue

            if (x, y) in fall_spawn_cells:
                color = (
                    palette.fall_zone_secondary
                    if use_secondary
                    else palette.fall_zone_primary
                )
            elif use_secondary:
                color = palette.floor_secondary
            else:
                color = palette.floor_primary
            lx, ly = (x * grid_snap, y * grid_snap)
            r = pygame.Rect(lx, ly, grid_snap, grid_snap)
            sr = apply_rect(r)
            if sr.colliderect(screen_rect):
                if use_secondary or (x, y) in fall_spawn_cells:
                    pygame.draw.rect(screen, color, sr)
                # Skip very bright white tiles (studio/export margins) to avoid noisy overlays.
                if min(color) < 245:
                    barcode_overlay = _get_floor_barcode_overlay_tile(
                        cell_size=grid_snap,
                        base_color=(
                            int(color[0]),
                            int(color[1]),
                            int(color[2]),
                        ),
                        stage_number=stage_number,
                    )
                    screen.blit(barcode_overlay, sr.topleft)
                # Floor ruin dressing: visual-only overlay for normal/fall-spawn floor tiles.
                variant = floor_ruin_cells.get((x, y))
                if variant is not None:
                    clutter_tier = _floor_clutter_tier_for_cell(
                        x=x, y=y, xs=xs, ys=ys, xe=xe, ye=ye
                    )
                    ruin_overlay = _get_floor_ruin_overlay_tile(
                        cell_size=grid_snap,
                        base_color=(
                            int(color[0]),
                            int(color[1]),
                            int(color[2]),
                        ),
                        wall_color=(
                            int(palette.inner_wall[0]),
                            int(palette.inner_wall[1]),
                            int(palette.inner_wall[2]),
                        ),
                        tier=clutter_tier,
                        variant=variant,
                    )
                    screen.blit(ruin_overlay, sr.topleft)

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
