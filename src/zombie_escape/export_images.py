from __future__ import annotations

import math
from pathlib import Path

import pygame

from .entities import SteelBeam
from .entities_constants import (
    BUDDY_RADIUS,
    CAR_HEIGHT,
    CAR_WIDTH,
    FLASHLIGHT_HEIGHT,
    FLASHLIGHT_WIDTH,
    FUEL_CAN_HEIGHT,
    FUEL_CAN_WIDTH,
    INTERNAL_WALL_BEVEL_DEPTH,
    PLAYER_RADIUS,
    SHOES_HEIGHT,
    SHOES_WIDTH,
    STEEL_BEAM_HEALTH,
    SURVIVOR_RADIUS,
    ZOMBIE_RADIUS,
)
from .level_constants import DEFAULT_TILE_SIZE
from .render_assets import (
    build_car_directional_surfaces,
    build_car_surface,
    build_flashlight_surface,
    build_fuel_can_surface,
    build_player_directional_surfaces,
    build_shoes_surface,
    build_survivor_directional_surfaces,
    build_zombie_directional_surfaces,
    draw_humanoid_hand,
    draw_humanoid_nose,
    paint_car_surface,
    paint_wall_surface,
    resolve_car_color,
    resolve_wall_colors,
)
from .colors import FALL_ZONE_FLOOR_PRIMARY
from .render_constants import (
    FALLING_ZOMBIE_COLOR,
    PITFALL_ABYSS_COLOR,
    PITFALL_EDGE_DEPTH_OFFSET,
    PITFALL_EDGE_METAL_COLOR,
    PITFALL_EDGE_STRIPE_COLOR,
    PITFALL_EDGE_STRIPE_SPACING,
    PITFALL_SHADOW_RIM_COLOR,
    PITFALL_SHADOW_WIDTH,
    ZOMBIE_NOSE_COLOR,
)

__all__ = ["export_images"]


def _ensure_pygame_ready() -> None:
    if not pygame.get_init():
        pygame.init()
    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        flags = pygame.HIDDEN if hasattr(pygame, "HIDDEN") else 0
        pygame.display.set_mode((1, 1), flags=flags)


def _save_surface(surface: pygame.Surface, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(path))


def _pick_directional_surface(
    surfaces: list[pygame.Surface], *, bin_index: int = 0
) -> pygame.Surface:
    if not surfaces:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    return surfaces[bin_index % len(surfaces)]


def _build_pitfall_tile(cell_size: int) -> pygame.Surface:
    surface = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
    rect = surface.get_rect()
    pygame.draw.rect(surface, PITFALL_ABYSS_COLOR, rect)

    for i in range(PITFALL_SHADOW_WIDTH):
        t = i / (PITFALL_SHADOW_WIDTH - 1.0)
        color = tuple(
            int(PITFALL_SHADOW_RIM_COLOR[j] * (1.0 - t) + PITFALL_ABYSS_COLOR[j] * t)
            for j in range(3)
        )
        pygame.draw.line(
            surface,
            color,
            (rect.x + i, rect.y),
            (rect.x + i, rect.bottom - 1),
        )
        pygame.draw.line(
            surface,
            color,
            (rect.right - 1 - i, rect.y),
            (rect.right - 1 - i, rect.bottom - 1),
        )

    edge_height = max(1, INTERNAL_WALL_BEVEL_DEPTH - PITFALL_EDGE_DEPTH_OFFSET)
    pygame.draw.rect(surface, PITFALL_EDGE_METAL_COLOR, (rect.x, rect.y, rect.w, edge_height))
    for sx in range(rect.x - edge_height, rect.right, PITFALL_EDGE_STRIPE_SPACING):
        pygame.draw.line(
            surface,
            PITFALL_EDGE_STRIPE_COLOR,
            (max(rect.x, sx), rect.y),
            (min(rect.right - 1, sx + edge_height), rect.y + edge_height - 1),
            width=2,
        )

    return surface


def export_images(output_dir: Path, *, cell_size: int = DEFAULT_TILE_SIZE) -> list[Path]:
    _ensure_pygame_ready()

    saved: list[Path] = []
    out = Path(output_dir)

    player = _pick_directional_surface(
        build_player_directional_surfaces(radius=PLAYER_RADIUS),
        bin_index=0,
    )
    player_path = out / "player.png"
    _save_surface(player, player_path)
    saved.append(player_path)

    zombie_base = _pick_directional_surface(
        build_zombie_directional_surfaces(radius=ZOMBIE_RADIUS, draw_hands=False),
        bin_index=0,
    )
    zombie_normal_path = out / "zombie-normal.png"
    _save_surface(zombie_base, zombie_normal_path)
    saved.append(zombie_normal_path)

    tracker = zombie_base.copy()
    draw_humanoid_nose(
        tracker,
        radius=ZOMBIE_RADIUS,
        angle_rad=0.0,
        color=ZOMBIE_NOSE_COLOR,
    )
    tracker_path = out / "zombie-tracker.png"
    _save_surface(tracker, tracker_path)
    saved.append(tracker_path)

    wall_follower = zombie_base.copy()
    draw_humanoid_hand(
        wall_follower,
        radius=ZOMBIE_RADIUS,
        angle_rad=math.pi / 2.0,
        color=ZOMBIE_NOSE_COLOR,
    )
    wall_path = out / "zombie-wall.png"
    _save_surface(wall_follower, wall_path)
    saved.append(wall_path)

    buddy = _pick_directional_surface(
        build_survivor_directional_surfaces(
            radius=BUDDY_RADIUS,
            is_buddy=True,
            draw_hands=True,
        ),
        bin_index=0,
    )
    buddy_path = out / "buddy.png"
    _save_surface(buddy, buddy_path)
    saved.append(buddy_path)

    survivor = _pick_directional_surface(
        build_survivor_directional_surfaces(
            radius=SURVIVOR_RADIUS,
            is_buddy=False,
            draw_hands=False,
        ),
        bin_index=0,
    )
    survivor_path = out / "survivor.png"
    _save_surface(survivor, survivor_path)
    saved.append(survivor_path)

    car_surface = build_car_surface(CAR_WIDTH, CAR_HEIGHT)
    car_color = resolve_car_color(health_ratio=1.0, appearance="default")
    paint_car_surface(
        car_surface,
        width=CAR_WIDTH,
        height=CAR_HEIGHT,
        color=car_color,
    )
    car = _pick_directional_surface(build_car_directional_surfaces(car_surface), bin_index=0)
    car_path = out / "car.png"
    _save_surface(car, car_path)
    saved.append(car_path)

    fuel = build_fuel_can_surface(FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT)
    fuel_path = out / "fuel.png"
    _save_surface(fuel, fuel_path)
    saved.append(fuel_path)

    flashlight = build_flashlight_surface(FLASHLIGHT_WIDTH, FLASHLIGHT_HEIGHT)
    flashlight_path = out / "flashlight.png"
    _save_surface(flashlight, flashlight_path)
    saved.append(flashlight_path)

    shoes = build_shoes_surface(SHOES_WIDTH, SHOES_HEIGHT)
    shoes_path = out / "shoes.png"
    _save_surface(shoes, shoes_path)
    saved.append(shoes_path)

    beam = SteelBeam(0, 0, cell_size, health=STEEL_BEAM_HEALTH, palette=None)
    beam_path = out / "steel-beam.png"
    _save_surface(beam.image, beam_path)
    saved.append(beam_path)

    inner_wall = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
    inner_fill, inner_border = resolve_wall_colors(
        health_ratio=1.0,
        palette_category="inner_wall",
        palette=None,
    )
    paint_wall_surface(
        inner_wall,
        fill_color=inner_fill,
        border_color=inner_border,
        bevel_depth=INTERNAL_WALL_BEVEL_DEPTH,
        bevel_mask=(False, False, False, False),
        draw_bottom_side=False,
        bottom_side_ratio=0.1,
        side_shade_ratio=0.9,
    )
    inner_wall_path = out / "wall-inner.png"
    _save_surface(inner_wall, inner_wall_path)
    saved.append(inner_wall_path)

    outer_wall = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
    outer_fill, outer_border = resolve_wall_colors(
        health_ratio=1.0,
        palette_category="outer_wall",
        palette=None,
    )
    paint_wall_surface(
        outer_wall,
        fill_color=outer_fill,
        border_color=outer_border,
        bevel_depth=0,
        bevel_mask=(False, False, False, False),
        draw_bottom_side=False,
        bottom_side_ratio=0.1,
        side_shade_ratio=0.9,
    )
    outer_wall_path = out / "wall-outer.png"
    _save_surface(outer_wall, outer_wall_path)
    saved.append(outer_wall_path)

    pitfall = _build_pitfall_tile(cell_size)
    pitfall_path = out / "pitfall.png"
    _save_surface(pitfall, pitfall_path)
    saved.append(pitfall_path)

    fall_radius = max(1, int(ZOMBIE_RADIUS))
    fall_size = fall_radius * 2
    falling = pygame.Surface((fall_size, fall_size), pygame.SRCALPHA)
    pygame.draw.circle(
        falling,
        FALLING_ZOMBIE_COLOR,
        (fall_radius, fall_radius),
        fall_radius,
    )
    falling_path = out / "falling-zombie.png"
    _save_surface(falling, falling_path)
    saved.append(falling_path)

    fall_zone = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
    fall_zone.fill(FALL_ZONE_FLOOR_PRIMARY)
    fall_zone_path = out / "fall-zone.png"
    _save_surface(fall_zone, fall_zone_path)
    saved.append(fall_zone_path)

    return saved
