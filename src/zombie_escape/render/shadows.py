from __future__ import annotations

import math

import pygame
from pygame import sprite, surface

from ..entities import (
    Camera,
    Car,
    Player,
    SpikyHouseplant,
    SteelBeam,
    Survivor,
    Zombie,
    ZombieDog,
)
from ..entities_constants import JUMP_SHADOW_OFFSET, ZOMBIE_RADIUS
from ..render_constants import (
    ENTITY_SHADOW_ALPHA,
    ENTITY_SHADOW_EDGE_SOFTNESS,
    ENTITY_SHADOW_RADIUS_MULT,
    FLASHLIGHT_FOG_SCALE_ONE,
    FLASHLIGHT_FOG_SCALE_TWO,
    FOG_RADIUS_SCALE,
    FOV_RADIUS,
    SHADOW_MIN_RATIO,
    SHADOW_OVERSAMPLE,
    SHADOW_RADIUS_RATIO,
    SHADOW_STEPS,
)

_SHADOW_TILE_CACHE: dict[tuple[int, int, float], surface.Surface] = {}
_SHADOW_LAYER_CACHE: dict[tuple[int, int], surface.Surface] = {}
_SHADOW_CIRCLE_CACHE: dict[tuple[int, int, float], surface.Surface] = {}


def _get_shadow_cell_surface(
    cell_size: int,
    alpha: int,
    *,
    edge_softness: float = 0.35,
) -> surface.Surface:
    key = (max(1, cell_size), max(0, min(255, alpha)), edge_softness)
    if key in _SHADOW_TILE_CACHE:
        return _SHADOW_TILE_CACHE[key]
    size = key[0]
    oversample = SHADOW_OVERSAMPLE
    render_size = size * oversample
    render_surf = pygame.Surface((render_size, render_size), pygame.SRCALPHA)
    base_alpha = key[1]
    if edge_softness <= 0:
        render_surf.fill((0, 0, 0, base_alpha))
        if oversample > 1:
            surf = pygame.transform.smoothscale(render_surf, (size, size))
        else:
            surf = render_surf
        _SHADOW_TILE_CACHE[key] = surf
        return surf

    softness = max(0.0, min(1.0, edge_softness))
    fade_band = max(1, int(render_size * softness))
    base_radius = max(1, int(render_size * SHADOW_RADIUS_RATIO))

    render_surf.fill((0, 0, 0, 0))
    steps = SHADOW_STEPS
    min_ratio = SHADOW_MIN_RATIO
    for idx in range(steps):
        t = idx / (steps - 1) if steps > 1 else 1.0
        inset = int(fade_band * t)
        rect_size = render_size - inset * 2
        if rect_size <= 0:
            continue
        radius = max(0, base_radius - inset)
        layer_alpha = int(base_alpha * (min_ratio + (1.0 - min_ratio) * t))
        pygame.draw.rect(
            render_surf,
            (0, 0, 0, layer_alpha),
            pygame.Rect(inset, inset, rect_size, rect_size),
            border_radius=radius,
        )

    if oversample > 1:
        surf = pygame.transform.smoothscale(render_surf, (size, size))
    else:
        surf = render_surf
    _SHADOW_TILE_CACHE[key] = surf
    return surf


def _get_shadow_layer(size: tuple[int, int]) -> surface.Surface:
    key = (max(1, size[0]), max(1, size[1]))
    if key in _SHADOW_LAYER_CACHE:
        return _SHADOW_LAYER_CACHE[key]
    layer = pygame.Surface(key, pygame.SRCALPHA)
    _SHADOW_LAYER_CACHE[key] = layer
    return layer


def _get_shadow_circle_surface(
    radius: int,
    alpha: int,
    *,
    edge_softness: float = 0.12,
) -> surface.Surface:
    key = (max(1, radius), max(0, min(255, alpha)), edge_softness)
    if key in _SHADOW_CIRCLE_CACHE:
        return _SHADOW_CIRCLE_CACHE[key]
    radius = key[0]
    oversample = SHADOW_OVERSAMPLE
    render_radius = radius * oversample
    render_size = render_radius * 2
    render_surf = pygame.Surface((render_size, render_size), pygame.SRCALPHA)
    base_alpha = key[1]
    if edge_softness <= 0:
        pygame.draw.circle(
            render_surf,
            (0, 0, 0, base_alpha),
            (render_radius, render_radius),
            render_radius,
        )
        if oversample > 1:
            surf = pygame.transform.smoothscale(render_surf, (radius * 2, radius * 2))
        else:
            surf = render_surf
        _SHADOW_CIRCLE_CACHE[key] = surf
        return surf

    softness = max(0.0, min(1.0, edge_softness))
    fade_band = max(1, int(render_radius * softness))
    steps = SHADOW_STEPS
    min_ratio = SHADOW_MIN_RATIO
    render_surf.fill((0, 0, 0, 0))
    for idx in range(steps):
        t = idx / (steps - 1) if steps > 1 else 1.0
        inset = int(fade_band * t)
        circle_radius = render_radius - inset
        if circle_radius <= 0:
            continue
        layer_alpha = int(base_alpha * (min_ratio + (1.0 - min_ratio) * t))
        pygame.draw.circle(
            render_surf,
            (0, 0, 0, layer_alpha),
            (render_radius, render_radius),
            circle_radius,
        )

    if oversample > 1:
        surf = pygame.transform.smoothscale(render_surf, (radius * 2, radius * 2))
    else:
        surf = render_surf
    _SHADOW_CIRCLE_CACHE[key] = surf
    return surf


def _abs_clip(value: float, min_v: float, max_v: float) -> float:
    value_sign = 1.0 if value >= 0.0 else -1.0
    value = abs(value)
    if value < min_v:
        value = min_v
    elif value > max_v:
        value = max_v
    return value_sign * value


def _draw_wall_shadows(
    shadow_layer: surface.Surface,
    camera: Camera,
    *,
    wall_cells: set[tuple[int, int]],
    wall_group: sprite.Group | None,
    outer_wall_cells: set[tuple[int, int]] | None,
    cell_size: int,
    light_source_pos: tuple[int, int] | None,
    alpha: int = 68,
) -> bool:
    if not wall_cells or cell_size <= 0 or light_source_pos is None:
        return False
    inner_wall_cells = set(wall_cells)
    if outer_wall_cells:
        inner_wall_cells.difference_update(outer_wall_cells)
    if wall_group and cell_size > 0:
        for wall in wall_group:
            if isinstance(wall, SteelBeam):
                cell_x = int(wall.rect.centerx // cell_size)
                cell_y = int(wall.rect.centery // cell_size)
                inner_wall_cells.add((cell_x, cell_y))
    if not inner_wall_cells:
        return False
    base_shadow_size = max(cell_size + 2, int(cell_size * 1.35))
    shadow_size = max(1, int(base_shadow_size * 1.5))
    shadow_surface = _get_shadow_cell_surface(
        shadow_size,
        alpha,
        edge_softness=0.12,
    )
    screen_rect = shadow_layer.get_rect()
    px, py = light_source_pos
    drew = False
    clip_max = shadow_size * 0.25
    for cell_x, cell_y in inner_wall_cells:
        world_x = cell_x * cell_size
        world_y = cell_y * cell_size
        wall_rect = pygame.Rect(world_x, world_y, cell_size, cell_size)
        wall_screen_rect = camera.apply_rect(wall_rect)
        if not wall_screen_rect.colliderect(screen_rect):
            continue
        center_x = world_x + cell_size / 2
        center_y = world_y + cell_size / 2
        dx = (center_x - px) * 0.5
        dy = (center_y - py) * 0.5
        dx = int(_abs_clip(dx, 0, clip_max))
        dy = int(_abs_clip(dy, 0, clip_max))
        shadow_rect = pygame.Rect(0, 0, shadow_size, shadow_size)
        shadow_rect.center = (
            int(center_x + dx),
            int(center_y + dy),
        )
        shadow_screen_rect = camera.apply_rect(shadow_rect)
        if not shadow_screen_rect.colliderect(screen_rect):
            continue
        shadow_layer.blit(
            shadow_surface,
            shadow_screen_rect.topleft,
            special_flags=pygame.BLEND_RGBA_MAX,
        )
        drew = True
    return drew


def _draw_entity_shadows(
    shadow_layer: surface.Surface,
    camera: Camera,
    all_sprites: sprite.LayeredUpdates,
    *,
    light_source_pos: tuple[float, float] | None,
    exclude_car: Car | None,
    outside_cells: set[tuple[int, int]] | None,
    cell_size: int,
    flashlight_count: int = 0,
    shadow_radius: int = int(ZOMBIE_RADIUS * ENTITY_SHADOW_RADIUS_MULT),
    alpha: int = ENTITY_SHADOW_ALPHA,
) -> bool:
    if light_source_pos is None or shadow_radius <= 0:
        return False
    if cell_size <= 0:
        outside_cells = None
    shadow_surface = _get_shadow_circle_surface(
        shadow_radius,
        alpha,
        edge_softness=ENTITY_SHADOW_EDGE_SOFTNESS,
    )
    screen_rect = _expanded_shadow_screen_rect(
        shadow_layer.get_rect(),
        flashlight_count,
    )
    px, py = light_source_pos
    drew = False
    for entity in all_sprites:
        if not entity.alive():
            continue
        if isinstance(entity, Player):
            continue
        if isinstance(entity, Car):
            if exclude_car is not None and entity is exclude_car:
                continue
        if not isinstance(entity, (Zombie, ZombieDog, Survivor, Car, SpikyHouseplant)):
            continue
        if outside_cells:
            cell = (
                int(entity.rect.centerx // cell_size),
                int(entity.rect.centery // cell_size),
            )
            if cell in outside_cells:
                continue
        cx, cy = entity.rect.center
        dx = cx - px
        dy = cy - py
        dist = math.hypot(dx, dy)
        if isinstance(entity, Car):
            car_shadow_radius = max(
                1, int(min(entity.rect.width, entity.rect.height) * 0.5 * 1.2)
            )
            surface_to_draw = _get_shadow_circle_surface(
                car_shadow_radius,
                alpha,
                edge_softness=ENTITY_SHADOW_EDGE_SOFTNESS,
            )
            offset_dist = max(1.0, car_shadow_radius * 0.6)
        else:
            surface_to_draw = shadow_surface
            offset_dist = max(1.0, shadow_radius * 0.6)
        if dist > 0.001:
            scale = offset_dist / dist
            offset_x = dx * scale
            offset_y = dy * scale
        else:
            offset_x = 0.0
            offset_y = 0.0

        jump_dy = 0.0
        if getattr(entity, "is_jumping", False):
            jump_dy = JUMP_SHADOW_OFFSET

        shadow_rect = surface_to_draw.get_rect(
            center=(int(cx + offset_x), int(cy + offset_y + jump_dy))
        )
        shadow_screen_rect = camera.apply_rect(shadow_rect)
        if not shadow_screen_rect.colliderect(screen_rect):
            continue
        shadow_layer.blit(
            surface_to_draw,
            shadow_screen_rect.topleft,
            special_flags=pygame.BLEND_RGBA_MAX,
        )
        drew = True
    return drew


def _draw_entity_drop_shadows(
    shadow_layer: surface.Surface,
    camera: Camera,
    all_sprites: sprite.LayeredUpdates,
    *,
    exclude_car: Car | None,
    outside_cells: set[tuple[int, int]] | None,
    cell_size: int,
    flashlight_count: int = 0,
    shadow_radius: int = int(ZOMBIE_RADIUS * ENTITY_SHADOW_RADIUS_MULT),
    alpha: int = ENTITY_SHADOW_ALPHA,
) -> bool:
    if shadow_radius <= 0:
        return False
    if cell_size <= 0:
        outside_cells = None
    shadow_surface = _get_shadow_circle_surface(
        shadow_radius,
        alpha,
        edge_softness=ENTITY_SHADOW_EDGE_SOFTNESS,
    )
    screen_rect = _expanded_shadow_screen_rect(
        shadow_layer.get_rect(),
        flashlight_count,
    )
    drew = False
    for entity in all_sprites:
        if not entity.alive():
            continue
        if isinstance(entity, Player):
            continue
        if isinstance(entity, Car):
            if exclude_car is not None and entity is exclude_car:
                continue
        if not isinstance(entity, (Zombie, ZombieDog, Survivor, Car, SpikyHouseplant)):
            continue
        if outside_cells:
            cell = (
                int(entity.rect.centerx // cell_size),
                int(entity.rect.centery // cell_size),
            )
            if cell in outside_cells:
                continue
        cx, cy = entity.rect.center

        jump_dy = 0.0
        if getattr(entity, "is_jumping", False):
            jump_dy = JUMP_SHADOW_OFFSET

        if isinstance(entity, Car):
            car_shadow_radius = max(
                1, int(min(entity.rect.width, entity.rect.height) * 0.5 * 1.2)
            )
            surface_to_draw = _get_shadow_circle_surface(
                car_shadow_radius,
                alpha,
                edge_softness=ENTITY_SHADOW_EDGE_SOFTNESS,
            )
        else:
            surface_to_draw = shadow_surface
        shadow_rect = surface_to_draw.get_rect(
            center=(int(cx), int(cy + jump_dy))
        )
        shadow_screen_rect = camera.apply_rect(shadow_rect)
        if not shadow_screen_rect.colliderect(screen_rect):
            continue
        shadow_layer.blit(
            surface_to_draw,
            shadow_screen_rect.topleft,
            special_flags=pygame.BLEND_RGBA_MAX,
        )
        drew = True
    return drew


def draw_entity_shadows_by_mode(
    shadow_layer: surface.Surface,
    camera: Camera,
    all_sprites: sprite.LayeredUpdates,
    *,
    dawn_shadow_mode: bool,
    light_source_pos: tuple[float, float] | None,
    exclude_car: Car | None,
    outside_cells: set[tuple[int, int]] | None,
    cell_size: int,
    flashlight_count: int = 0,
    shadow_radius: int = int(ZOMBIE_RADIUS * ENTITY_SHADOW_RADIUS_MULT),
    alpha: int = ENTITY_SHADOW_ALPHA,
) -> bool:
    if dawn_shadow_mode:
        return _draw_entity_drop_shadows(
            shadow_layer,
            camera,
            all_sprites,
            exclude_car=exclude_car,
            outside_cells=outside_cells,
            cell_size=cell_size,
            flashlight_count=flashlight_count,
            shadow_radius=shadow_radius,
            alpha=alpha,
        )
    return _draw_entity_shadows(
        shadow_layer,
        camera,
        all_sprites,
        light_source_pos=light_source_pos,
        exclude_car=exclude_car,
        outside_cells=outside_cells,
        cell_size=cell_size,
        flashlight_count=flashlight_count,
        shadow_radius=shadow_radius,
        alpha=alpha,
    )


def _expanded_shadow_screen_rect(
    screen_rect: pygame.Rect,
    flashlight_count: int,
) -> pygame.Rect:
    count = max(0, int(flashlight_count))
    if count <= 0:
        scale = FOG_RADIUS_SCALE
    elif count == 1:
        scale = FLASHLIGHT_FOG_SCALE_ONE
    else:
        scale = FLASHLIGHT_FOG_SCALE_TWO
    extra_scale = max(0.0, scale - FOG_RADIUS_SCALE)
    margin = int(FOV_RADIUS * extra_scale)
    if margin <= 0:
        return screen_rect
    return screen_rect.inflate(margin * 2, margin * 2)


def _draw_single_entity_shadow(
    shadow_layer: surface.Surface,
    camera: Camera,
    *,
    entity: pygame.sprite.Sprite | None,
    light_source_pos: tuple[float, float] | None,
    outside_cells: set[tuple[int, int]] | None,
    cell_size: int,
    shadow_radius: int,
    alpha: int,
    edge_softness: float = ENTITY_SHADOW_EDGE_SOFTNESS,
    offset_scale: float = 1.0,
) -> bool:
    if (
        entity is None
        or not entity.alive()
        or light_source_pos is None
        or shadow_radius <= 0
    ):
        return False
    if outside_cells and cell_size > 0:
        cell = (
            int(entity.rect.centerx // cell_size),
            int(entity.rect.centery // cell_size),
        )
        if cell in outside_cells:
            return False
    shadow_surface = _get_shadow_circle_surface(
        shadow_radius,
        alpha,
        edge_softness=edge_softness,
    )
    screen_rect = shadow_layer.get_rect()
    px, py = light_source_pos
    cx, cy = entity.rect.center
    dx = cx - px
    dy = cy - py
    dist = math.hypot(dx, dy)
    offset_dist = max(1.0, shadow_radius * 0.6) * max(0.0, offset_scale)
    if dist > 0.001:
        scale = offset_dist / dist
        offset_x = dx * scale
        offset_y = dy * scale
    else:
        offset_x = 0.0
        offset_y = 0.0

    jump_dy = 0.0
    if getattr(entity, "is_jumping", False):
        jump_dy = JUMP_SHADOW_OFFSET

    shadow_rect = shadow_surface.get_rect(
        center=(int(cx + offset_x), int(cy + offset_y + jump_dy))
    )
    shadow_screen_rect = camera.apply_rect(shadow_rect)
    if not shadow_screen_rect.colliderect(screen_rect):
        return False
    shadow_layer.blit(
        shadow_surface,
        shadow_screen_rect.topleft,
        special_flags=pygame.BLEND_RGBA_MAX,
    )
    return True


def draw_single_entity_shadow_by_mode(
    shadow_layer: surface.Surface,
    camera: Camera,
    *,
    entity: pygame.sprite.Sprite | None,
    dawn_shadow_mode: bool,
    light_source_pos: tuple[float, float] | None,
    outside_cells: set[tuple[int, int]] | None,
    cell_size: int,
    shadow_radius: int,
    alpha: int,
    edge_softness: float = ENTITY_SHADOW_EDGE_SOFTNESS,
    offset_scale: float = 1.0,
) -> bool:
    if dawn_shadow_mode:
        return _draw_single_entity_drop_shadow(
            shadow_layer,
            camera,
            entity=entity,
            outside_cells=outside_cells,
            cell_size=cell_size,
            shadow_radius=shadow_radius,
            alpha=alpha,
            edge_softness=edge_softness,
        )
    return _draw_single_entity_shadow(
        shadow_layer,
        camera,
        entity=entity,
        light_source_pos=light_source_pos,
        outside_cells=outside_cells,
        cell_size=cell_size,
        shadow_radius=shadow_radius,
        alpha=alpha,
        edge_softness=edge_softness,
        offset_scale=offset_scale,
    )


def _draw_single_entity_drop_shadow(
    shadow_layer: surface.Surface,
    camera: Camera,
    *,
    entity: pygame.sprite.Sprite | None,
    outside_cells: set[tuple[int, int]] | None,
    cell_size: int,
    shadow_radius: int,
    alpha: int,
    edge_softness: float = ENTITY_SHADOW_EDGE_SOFTNESS,
) -> bool:
    if entity is None or not entity.alive() or shadow_radius <= 0:
        return False
    if outside_cells and cell_size > 0:
        cell = (
            int(entity.rect.centerx // cell_size),
            int(entity.rect.centery // cell_size),
        )
        if cell in outside_cells:
            return False
    shadow_surface = _get_shadow_circle_surface(
        shadow_radius,
        alpha,
        edge_softness=edge_softness,
    )
    screen_rect = shadow_layer.get_rect()
    cx, cy = entity.rect.center

    jump_dy = 0.0
    if getattr(entity, "is_jumping", False):
        jump_dy = JUMP_SHADOW_OFFSET

    shadow_rect = shadow_surface.get_rect(center=(int(cx), int(cy + jump_dy)))
    shadow_screen_rect = camera.apply_rect(shadow_rect)
    if not shadow_screen_rect.colliderect(screen_rect):
        return False
    shadow_layer.blit(
        shadow_surface,
        shadow_screen_rect.topleft,
        special_flags=pygame.BLEND_RGBA_MAX,
    )
    return True
