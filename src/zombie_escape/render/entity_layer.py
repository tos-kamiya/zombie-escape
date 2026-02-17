from __future__ import annotations

import math

import pygame
from pygame import sprite, surface

from ..colors import YELLOW
from ..entities_constants import ZOMBIE_RADIUS
from ..render_assets import (
    build_zombie_directional_surfaces,
    draw_lineformer_direction_arm,
)
from ..render_constants import ZOMBIE_OUTLINE_COLOR

_LINEFORMER_MARKER_SURFACES: dict[int, list[surface.Surface]] = {}


def _get_lineformer_marker_surfaces(radius: int) -> list[surface.Surface]:
    cached = _LINEFORMER_MARKER_SURFACES.get(radius)
    if cached is not None:
        return cached
    base_surfaces = build_zombie_directional_surfaces(radius, draw_hands=False)
    bins = len(base_surfaces)
    step = math.tau / bins
    surfaces: list[surface.Surface] = []
    for idx, base_surface in enumerate(base_surfaces):
        marker_surface = base_surface.copy()
        draw_lineformer_direction_arm(
            marker_surface,
            radius=radius,
            angle_rad=idx * step,
            color=ZOMBIE_OUTLINE_COLOR,
        )
        surfaces.append(marker_surface)
    _LINEFORMER_MARKER_SURFACES[radius] = surfaces
    return surfaces


def _draw_fuel_indicator(
    screen: surface.Surface,
    player_screen_rect: pygame.Rect,
    *,
    has_fuel: bool,
    has_empty_fuel_can: bool,
    in_car: bool,
) -> None:
    if in_car:
        return
    if not has_fuel and not has_empty_fuel_can:
        return
    indicator_size = 4
    padding = 1
    indicator_rect = pygame.Rect(
        player_screen_rect.right - indicator_size - padding,
        player_screen_rect.bottom - indicator_size - padding,
        indicator_size,
        indicator_size,
    )
    if has_fuel:
        fill_color = YELLOW
        border_color = (180, 160, 40)
    else:
        fill_color = (235, 235, 235)
        border_color = (180, 180, 180)
    pygame.draw.rect(screen, fill_color, indicator_rect)
    pygame.draw.rect(screen, border_color, indicator_rect, width=1)


def _draw_entities(
    screen: surface.Surface,
    sprite_draw_data: list[tuple[sprite.Sprite, pygame.Rect]],
    player: sprite.Sprite,
    *,
    has_fuel: bool,
    has_empty_fuel_can: bool,
    show_fuel_indicator: bool,
) -> None:
    screen_rect_inflated = screen.get_rect().inflate(100, 100)
    for entity, sprite_screen_rect in sprite_draw_data:
        if sprite_screen_rect.colliderect(screen_rect_inflated):
            screen.blit(entity.image, sprite_screen_rect)
        if entity is player:
            if show_fuel_indicator:
                _draw_fuel_indicator(
                    screen,
                    sprite_screen_rect,
                    has_fuel=has_fuel,
                    has_empty_fuel_can=has_empty_fuel_can,
                    in_car=player.in_car,
                )


def _draw_lineformer_train_markers(
    screen: surface.Surface,
    marker_draw_data: list[tuple[int, int, float]],
) -> None:
    if not marker_draw_data:
        return
    marker_radius = max(2, int(ZOMBIE_RADIUS))
    marker_surfaces = _get_lineformer_marker_surfaces(marker_radius)
    bins = len(marker_surfaces)
    angle_step = math.tau / bins
    screen_rect_inflated = screen.get_rect().inflate(100, 100)
    for center_x, center_y, angle_rad in marker_draw_data:
        bin_idx = int(round(angle_rad / angle_step)) % bins
        marker_image = marker_surfaces[bin_idx]
        marker_rect = marker_image.get_rect(center=(center_x, center_y))
        if not marker_rect.colliderect(screen_rect_inflated):
            continue
        screen.blit(marker_image, marker_rect)
