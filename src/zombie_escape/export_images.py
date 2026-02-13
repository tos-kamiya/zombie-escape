from __future__ import annotations

import math
from pathlib import Path

import pygame

from .colors import STUDIO_AMBIENT_PALETTE_KEY, get_environment_palette
from .entities import (
    Car,
    EmptyFuelCan,
    Flashlight,
    FuelCan,
    FuelStation,
    PatrolBot,
    Player,
    RubbleWall,
    Shoes,
    SteelBeam,
    Survivor,
    Wall,
    Zombie,
    ZombieDog,
)
from .entities_constants import (
    INTERNAL_WALL_BEVEL_DEPTH,
    PATROL_BOT_COLLISION_RADIUS,
    STEEL_BEAM_HEALTH,
    ZOMBIE_RADIUS,
    MovingFloorDirection,
    ZombieKind,
)
from .gameplay.state import initialize_game_state
from .level_constants import DEFAULT_CELL_SIZE
from .models import FallingEntity, FuelProgress, Stage
from .render.core import _draw_entities, _draw_falling_fx, _draw_play_area
from .render_constants import build_render_assets
from .render.shadows import _get_shadow_layer, draw_single_entity_shadow_by_mode
from .render_constants import ENTITY_SHADOW_ALPHA, ENTITY_SHADOW_EDGE_SOFTNESS
from .screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH

__all__ = ["export_images"]


def _ensure_pygame_ready() -> None:
    if not pygame.get_init():
        pygame.init()
    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        flags = pygame.HIDDEN if hasattr(pygame, "HIDDEN") else 0
        pygame.display.set_mode((1, 1), flags=flags)


def _save_surface(surface: pygame.Surface, path: Path, *, scale: int = 1) -> None:
    if scale != 1:
        width, height = surface.get_size()
        surface = pygame.transform.scale(surface, (width * scale, height * scale))
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(path))


def _studio_grid_size(cell_size: int) -> tuple[int, int]:
    cols = max(3, math.ceil(SCREEN_WIDTH / cell_size) + 2)
    rows = max(3, math.ceil(SCREEN_HEIGHT / cell_size) + 2)
    return cols, rows


def _build_studio_stage(cell_size: int) -> Stage:
    cols, rows = _studio_grid_size(cell_size)
    return Stage(
        id="studio",
        name_key="studio",
        description_key="studio",
        available=False,
        cell_size=cell_size,
        grid_cols=cols,
        grid_rows=rows,
    )


def _build_studio_game_data(cell_size: int):
    stage = _build_studio_stage(cell_size)
    game_data = initialize_game_state({}, stage)
    state = game_data.state
    state.ambient_palette_key = STUDIO_AMBIENT_PALETTE_KEY
    state.fuel_progress = FuelProgress.NONE
    state.flashlight_count = 0
    state.shoes_count = 0
    state.timed_message = None
    state.fade_in_started_at_ms = None
    state.show_fps = False
    state.debug_mode = False
    state.clock.elapsed_ms = 0
    state.falling_zombies = []
    state.dust_rings = []
    state.decay_effects = []
    state.footprints = []
    return game_data


def _center_camera(camera: object, target_rect: pygame.Rect) -> None:
    dummy = pygame.sprite.Sprite()
    dummy.rect = target_rect.copy()
    camera.update(dummy)


def _render_studio_snapshot(
    *,
    cell_size: int,
    target_rect: pygame.Rect,
    sprites: list[pygame.sprite.Sprite] | None = None,
    pitfall_cells: set[tuple[int, int]] | None = None,
    fall_spawn_cells: set[tuple[int, int]] | None = None,
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection] | None = None,
    falling_zombies: list[FallingEntity] | None = None,
    enable_shadows: bool = False,
) -> pygame.Surface:
    game_data = _build_studio_game_data(cell_size)
    assets = build_render_assets(cell_size)
    screen = pygame.Surface((assets.screen_width, assets.screen_height), pygame.SRCALPHA)

    layout = game_data.layout
    layout.pitfall_cells = pitfall_cells or set()
    layout.fall_spawn_cells = fall_spawn_cells or set()
    layout.moving_floor_cells = moving_floor_cells or {}

    sprites = sprites or []
    player = None
    for sprite in sprites:
        if isinstance(sprite, Player):
            player = sprite
        game_data.groups.all_sprites.add(sprite)
    if player is None:
        player = Player(-cell_size, -cell_size)
    game_data.player = player

    padding_x = max(1, int(round(target_rect.width * 0.3)))
    padding_y = max(1, int(round(target_rect.height * 0.3)))
    framing_rect = target_rect.inflate(padding_x, padding_y)

    _center_camera(game_data.camera, framing_rect)

    palette = get_environment_palette(game_data.state.ambient_palette_key)
    screen.fill(palette.outside)
    _draw_play_area(
        screen,
        game_data.camera,
        assets,
        palette,
        layout.field_rect,
        layout.outside_cells,
        layout.fall_spawn_cells,
        layout.pitfall_cells,
        layout.moving_floor_cells,
        set(),
        game_data.cell_size,
        elapsed_ms=int(game_data.state.clock.elapsed_ms),
    )
    if enable_shadows:
        shadow_layer = _get_shadow_layer(screen.get_size())
        shadow_layer.fill((0, 0, 0, 0))
        light_offset = max(4, int(min(target_rect.width, target_rect.height) * 0.14))
        light_source_pos = (
            float(target_rect.centerx - light_offset),
            float(target_rect.centery + light_offset),
        )
        shadow_alpha = max(1, int(ENTITY_SHADOW_ALPHA * 2.2))
        drew_shadow = False
        for sprite in sprites:
            if not sprite.alive():
                continue
            if isinstance(sprite, PatrolBot):
                shadow_radius = max(1, int(PATROL_BOT_COLLISION_RADIUS * 1.2))
                offset_scale = 1 / 3
            else:
                sprite_radius = getattr(sprite, "radius", None)
                if sprite_radius is None:
                    shadow_radius = max(1, int(min(sprite.rect.width, sprite.rect.height) * 0.5 * 1.2))
                else:
                    shadow_radius = max(1, int(sprite_radius * 1.8))
                offset_scale = 1.0
            drew_shadow |= draw_single_entity_shadow_by_mode(
                shadow_layer,
                game_data.camera,
                entity=sprite,
                dawn_shadow_mode=False,
                light_source_pos=light_source_pos,
                outside_cells=layout.outside_cells,
                cell_size=game_data.cell_size,
                shadow_radius=shadow_radius,
                alpha=shadow_alpha,
                edge_softness=ENTITY_SHADOW_EDGE_SOFTNESS,
                offset_scale=offset_scale,
            )
        if drew_shadow:
            screen.blit(shadow_layer, (0, 0))
    if falling_zombies:
        game_data.state.falling_zombies = falling_zombies
        _draw_falling_fx(
            screen,
            game_data.camera,
            game_data.state.falling_zombies,
            game_data.state.flashlight_count,
            game_data.state.dust_rings,
            int(game_data.state.clock.elapsed_ms),
        )
    _draw_entities(
        screen,
        game_data.camera,
        game_data.groups.all_sprites,
        player,
        has_fuel=(game_data.state.fuel_progress == FuelProgress.FULL_CAN),
        has_empty_fuel_can=(game_data.state.fuel_progress == FuelProgress.EMPTY_CAN),
        show_fuel_indicator=False,
    )

    screen_rect = game_data.camera.apply_rect(framing_rect)
    return screen.subsurface(screen_rect).copy()


def export_images(
    output_dir: Path, *, cell_size: int = DEFAULT_CELL_SIZE, output_scale: int = 4
) -> list[Path]:
    _ensure_pygame_ready()

    saved: list[Path] = []
    out = Path(output_dir)

    cols, rows = _studio_grid_size(cell_size)
    center_x = (cols * cell_size) // 2
    center_y = (rows * cell_size) // 2
    cell_x = cols // 2
    cell_y = rows // 2

    player = Player(center_x, center_y)
    player_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=player.rect,
        sprites=[player],
        enable_shadows=True,
    )
    player_path = out / "player.png"
    _save_surface(player_surface, player_path, scale=output_scale)
    saved.append(player_path)

    zombie = Zombie(center_x, center_y, kind=ZombieKind.NORMAL)
    zombie_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=zombie.rect,
        sprites=[zombie],
        enable_shadows=True,
    )
    zombie_normal_path = out / "zombie-normal.png"
    _save_surface(zombie_surface, zombie_normal_path, scale=output_scale)
    saved.append(zombie_normal_path)

    tracker = Zombie(center_x, center_y, kind=ZombieKind.TRACKER)
    tracker._apply_render_overlays()
    tracker_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=tracker.rect,
        sprites=[tracker],
        enable_shadows=True,
    )
    tracker_path = out / "zombie-tracker.png"
    _save_surface(tracker_surface, tracker_path, scale=output_scale)
    saved.append(tracker_path)

    wall_hugging = Zombie(center_x, center_y, kind=ZombieKind.WALL_HUGGER)
    wall_hugging.wall_hug_side = 1.0
    wall_hugging.wall_hug_last_side_has_wall = True
    wall_hugging._apply_render_overlays()
    wall_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=wall_hugging.rect,
        sprites=[wall_hugging],
        enable_shadows=True,
    )
    wall_path = out / "zombie-wall.png"
    _save_surface(wall_surface, wall_path, scale=output_scale)
    saved.append(wall_path)

    lineformer = Zombie(center_x, center_y, kind=ZombieKind.LINEFORMER)
    lineformer.lineformer_target_pos = (center_x + cell_size, center_y)
    lineformer._apply_render_overlays()
    lineformer_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=lineformer.rect,
        sprites=[lineformer],
        enable_shadows=True,
    )
    lineformer_path = out / "zombie-lineformer.png"
    _save_surface(lineformer_surface, lineformer_path, scale=output_scale)
    saved.append(lineformer_path)

    zombie_dog = ZombieDog(center_x, center_y)
    zombie_dog_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=zombie_dog.rect,
        sprites=[zombie_dog],
        enable_shadows=True,
    )
    zombie_dog_path = out / "zombie-dog.png"
    _save_surface(zombie_dog_surface, zombie_dog_path, scale=output_scale)
    saved.append(zombie_dog_path)

    buddy = Survivor(center_x, center_y, is_buddy=True)
    buddy_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=buddy.rect,
        sprites=[buddy],
        enable_shadows=True,
    )
    buddy_path = out / "buddy.png"
    _save_surface(buddy_surface, buddy_path, scale=output_scale)
    saved.append(buddy_path)

    survivor = Survivor(center_x, center_y, is_buddy=False)
    survivor_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=survivor.rect,
        sprites=[survivor],
        enable_shadows=True,
    )
    survivor_path = out / "survivor.png"
    _save_surface(survivor_surface, survivor_path, scale=output_scale)
    saved.append(survivor_path)

    car = Car(center_x, center_y, appearance="default")
    car._set_facing_bin(0)
    car_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=car.rect,
        sprites=[car],
        enable_shadows=True,
    )
    car_path = out / "car.png"
    _save_surface(car_surface, car_path, scale=output_scale)
    saved.append(car_path)

    patrol_bot = PatrolBot(center_x, center_y)
    patrol_bot_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=patrol_bot.rect,
        sprites=[patrol_bot],
        enable_shadows=True,
    )
    patrol_bot_path = out / "patrol-bot.png"
    _save_surface(patrol_bot_surface, patrol_bot_path, scale=output_scale)
    saved.append(patrol_bot_path)

    fuel = FuelCan(center_x, center_y)
    fuel_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=fuel.rect,
        sprites=[fuel],
    )
    fuel_path = out / "fuel.png"
    _save_surface(fuel_surface, fuel_path, scale=output_scale)
    saved.append(fuel_path)

    empty_fuel_can = EmptyFuelCan(center_x, center_y)
    empty_fuel_can_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=empty_fuel_can.rect,
        sprites=[empty_fuel_can],
    )
    empty_fuel_can_path = out / "empty-fuel-can.png"
    _save_surface(empty_fuel_can_surface, empty_fuel_can_path, scale=output_scale)
    saved.append(empty_fuel_can_path)

    fuel_station = FuelStation(center_x, center_y)
    fuel_station_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=fuel_station.rect,
        sprites=[fuel_station],
    )
    fuel_station_path = out / "fuel-station.png"
    _save_surface(fuel_station_surface, fuel_station_path, scale=output_scale)
    saved.append(fuel_station_path)

    flashlight = Flashlight(center_x, center_y)
    flashlight_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=flashlight.rect,
        sprites=[flashlight],
    )
    flashlight_path = out / "flashlight.png"
    _save_surface(flashlight_surface, flashlight_path, scale=output_scale)
    saved.append(flashlight_path)

    shoes = Shoes(center_x, center_y)
    shoes_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=shoes.rect,
        sprites=[shoes],
    )
    shoes_path = out / "shoes.png"
    _save_surface(shoes_surface, shoes_path, scale=output_scale)
    saved.append(shoes_path)

    beam = SteelBeam(
        center_x - cell_size // 2,
        center_y - cell_size // 2,
        cell_size,
        health=STEEL_BEAM_HEALTH,
        palette=None,
    )
    beam_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=beam.rect,
        sprites=[beam],
    )
    beam_path = out / "steel-beam.png"
    _save_surface(beam_surface, beam_path, scale=output_scale)
    saved.append(beam_path)

    inner_wall = Wall(
        center_x - cell_size // 2,
        center_y - cell_size // 2,
        cell_size,
        cell_size,
        palette_category="inner_wall",
        bevel_depth=INTERNAL_WALL_BEVEL_DEPTH,
        bevel_mask=(True, True, True, True),
        draw_bottom_side=True,
        bottom_side_ratio=0.1,
        side_shade_ratio=0.9,
    )
    inner_wall_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=inner_wall.rect,
        sprites=[inner_wall],
    )
    inner_wall_path = out / "wall-inner.png"
    _save_surface(inner_wall_surface, inner_wall_path, scale=output_scale)
    saved.append(inner_wall_path)

    rubble_wall = RubbleWall(
        center_x - cell_size // 2,
        center_y - cell_size // 2,
        cell_size,
        cell_size,
        palette_category="inner_wall",
    )
    rubble_wall_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=rubble_wall.rect,
        sprites=[rubble_wall],
    )
    rubble_wall_path = out / "wall-rubble.png"
    _save_surface(rubble_wall_surface, rubble_wall_path, scale=output_scale)
    saved.append(rubble_wall_path)

    outer_wall = Wall(
        center_x - cell_size // 2,
        center_y - cell_size // 2,
        cell_size,
        cell_size,
        palette_category="outer_wall",
        bevel_depth=0,
        bevel_mask=(True, True, True, True),
        draw_bottom_side=True,
        bottom_side_ratio=0.1,
        side_shade_ratio=0.9,
    )
    outer_wall_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=outer_wall.rect,
        sprites=[outer_wall],
    )
    outer_wall_path = out / "wall-outer.png"
    _save_surface(outer_wall_surface, outer_wall_path, scale=output_scale)
    saved.append(outer_wall_path)

    pitfall_rect = pygame.Rect(
        cell_x * cell_size,
        cell_y * cell_size,
        cell_size,
        cell_size,
    )
    pitfall_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=pitfall_rect,
        pitfall_cells={(cell_x, cell_y)},
    )
    pitfall_path = out / "pitfall.png"
    _save_surface(pitfall_surface, pitfall_path, scale=output_scale)
    saved.append(pitfall_path)

    fall_target = (center_x, center_y)
    falling = FallingEntity(
        start_pos=fall_target,
        target_pos=fall_target,
        started_at_ms=0,
        pre_fx_ms=0,
        fall_duration_ms=1000,
        dust_duration_ms=0,
        kind=None,
        mode="pitfall",
    )
    fall_rect = pygame.Rect(0, 0, ZOMBIE_RADIUS * 2, ZOMBIE_RADIUS * 2)
    fall_rect.center = fall_target
    falling_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=fall_rect,
        falling_zombies=[falling],
    )
    falling_path = out / "falling-zombie.png"
    _save_surface(falling_surface, falling_path, scale=output_scale)
    saved.append(falling_path)

    fall_zone_cell_x = max(0, min(cols - 4, cell_x - 2))
    fall_zone_cell_y = max(0, min(rows - 4, cell_y - 2))
    fall_zone_cells = {
        (fall_zone_cell_x + dx, fall_zone_cell_y + dy)
        for dx in range(4)
        for dy in range(4)
    }
    fall_zone_rect = pygame.Rect(
        fall_zone_cell_x * cell_size,
        fall_zone_cell_y * cell_size,
        cell_size * 4,
        cell_size * 4,
    )
    fall_zone_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=fall_zone_rect,
        fall_spawn_cells=fall_zone_cells,
    )
    fall_zone_path = out / "fall-zone.png"
    _save_surface(fall_zone_surface, fall_zone_path, scale=output_scale)
    saved.append(fall_zone_path)

    moving_floor_rect = pygame.Rect(
        cell_x * cell_size,
        cell_y * cell_size,
        cell_size,
        cell_size,
    )
    moving_floor_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=moving_floor_rect,
        moving_floor_cells={(cell_x, cell_y): MovingFloorDirection.RIGHT},
    )
    moving_floor_path = out / "moving-floor.png"
    _save_surface(moving_floor_surface, moving_floor_path, scale=output_scale)
    saved.append(moving_floor_path)

    return saved
