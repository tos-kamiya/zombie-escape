from __future__ import annotations

import math
import random
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
    ReinforcedWall,
    RubbleWall,
    Shoes,
    SteelBeam,
    Survivor,
    Wall,
    Zombie,
    ZombieDog,
    SpikyPlant,
)
from .entities_constants import (
    INTERNAL_WALL_BEVEL_DEPTH,
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
from .render_constants import ENTITY_SHADOW_ALPHA, ENTITY_SHADOW_EDGE_SOFTNESS
from .render.shadows import _get_shadow_layer, draw_single_entity_shadow_by_mode
from .render.world_tiles import build_floor_ruin_cells
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
        zombie_normal_ratio=1.0,
    )


def _build_studio_game_data(cell_size: int):
    stage = _build_studio_stage(cell_size)
    game_data = initialize_game_state(stage)
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
    fire_floor_cells: set[tuple[int, int]] | None = None,
    fall_spawn_cells: set[tuple[int, int]] | None = None,
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection] | None = None,
    puddle_cells: set[tuple[int, int]] | None = None,
    falling_zombies: list[FallingEntity] | None = None,
    enable_shadows: bool = False,
    ambient_palette_key: str | None = STUDIO_AMBIENT_PALETTE_KEY,
    wall_rubble_ratio: float | None = None,
    stage_number: int = 0,
) -> pygame.Surface:
    game_data = _build_studio_game_data(cell_size)
    game_data.state.ambient_palette_key = ambient_palette_key
    assets = build_render_assets(cell_size)
    screen = pygame.Surface(
        (assets.screen_width, assets.screen_height), pygame.SRCALPHA
    )

    layout = game_data.layout
    layout.pitfall_cells = pitfall_cells or set()
    layout.fire_floor_cells = fire_floor_cells or set()
    layout.metal_floor_cells = set()
    layout.fall_spawn_cells = fall_spawn_cells or set()
    layout.moving_floor_cells = moving_floor_cells or {}
    layout.puddle_cells = puddle_cells or set()
    resolved_rubble_ratio = (
        float(wall_rubble_ratio)
        if wall_rubble_ratio is not None
        else float(game_data.stage.wall_rubble_ratio)
    )
    floor_ruin_candidates = [
        (x, y)
        for y in range(layout.grid_rows)
        for x in range(layout.grid_cols)
        if (x, y) not in layout.outside_cells
        and (x, y) not in layout.pitfall_cells
        and (x, y) not in layout.fire_floor_cells
        and (x, y) not in layout.metal_floor_cells
        and (x, y) not in layout.puddle_cells
        and (x, y) not in layout.moving_floor_cells
    ]
    layout.floor_ruin_cells = build_floor_ruin_cells(
        candidate_cells=floor_ruin_candidates,
        rubble_ratio=resolved_rubble_ratio,
    )

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
        game_data.camera.apply_rect,
        pygame.Rect(
            -game_data.camera.camera.x,
            -game_data.camera.camera.y,
            assets.screen_width,
            assets.screen_height,
        ),
        assets,
        palette,
        layout.field_rect,
        layout.outside_cells,
        layout.fall_spawn_cells,
        layout.pitfall_cells,
        layout.fire_floor_cells,
        layout.metal_floor_cells,
        layout.puddle_cells,
        layout.moving_floor_cells,
        layout.floor_ruin_cells,
        set(),
        game_data.cell_size,
        max(0, int(stage_number)),
        elapsed_ms=int(game_data.state.clock.elapsed_ms),
        flashlight_count=game_data.state.flashlight_count,
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
            shadow_radius_raw = getattr(sprite, "shadow_radius", None)
            if shadow_radius_raw is not None:
                shadow_radius = max(0, int(shadow_radius_raw))
            else:
                collision_radius = getattr(sprite, "collision_radius", None)
                if collision_radius is not None:
                    shadow_radius = max(1, int(float(collision_radius) * 1.2))
                else:
                    shadow_radius = max(
                        1, int(min(sprite.rect.width, sprite.rect.height) * 0.5 * 1.2)
                    )
            offset_scale = float(getattr(sprite, "shadow_offset_scale", 1.0))
            drew_shadow |= draw_single_entity_shadow_by_mode(
                shadow_layer,
                game_data.camera.apply_rect,
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
            game_data.camera.apply_rect,
            game_data.state.falling_zombies,
            game_data.state.flashlight_count,
            game_data.state.dust_rings,
            int(game_data.state.clock.elapsed_ms),
        )
    _draw_entities(
        screen,
        [
            (entity, game_data.camera.apply_rect(entity.rect))
            for entity in game_data.groups.all_sprites
        ],
        player,
        has_fuel=(game_data.state.fuel_progress == FuelProgress.FULL_CAN),
        has_empty_fuel_can=(game_data.state.fuel_progress == FuelProgress.EMPTY_CAN),
        show_fuel_indicator=False,
    )

    screen_rect = game_data.camera.apply_rect(framing_rect)
    clipped = screen_rect.clip(pygame.Rect(0, 0, assets.screen_width, assets.screen_height))
    if clipped.width <= 0 or clipped.height <= 0:
        return screen.copy()
    return screen.subsurface(clipped).copy()


def _center_target_rect(*, cell_size: int, cols: int, rows: int) -> pygame.Rect:
    studio_cols, studio_rows = _studio_grid_size(cell_size)
    center_cell_x = studio_cols // 2
    center_cell_y = studio_rows // 2
    left = (center_cell_x - cols // 2) * cell_size
    top = (center_cell_y - rows // 2) * cell_size
    return pygame.Rect(left, top, cols * cell_size, rows * cell_size)


def _build_fall_spawn_cells_for_rect(
    target_rect: pygame.Rect, *, cell_size: int
) -> set[tuple[int, int]]:
    x0 = target_rect.left // cell_size
    y0 = target_rect.top // cell_size
    x1 = target_rect.right // cell_size
    y1 = target_rect.bottom // cell_size

    cells: set[tuple[int, int]] = set()
    for y in range(y0, y1):
        for x in range(x0, x1):
            local_x = x - x0
            local_y = y - y0
            # Sparse pattern so floor decoration differences are visible.
            if (local_x + local_y) % 5 == 0:
                cells.add((x, y))
            elif local_x % 7 == 0 and (local_y % 3) == 1:
                cells.add((x, y))
    return cells


def _render_floor_ruin_explainer(*, cell_size: int) -> pygame.Surface:
    cols = max(8, int((SCREEN_WIDTH * 0.55) // cell_size))
    rows = max(6, int((SCREEN_HEIGHT * 0.55) // cell_size))
    target_rect = _center_target_rect(cell_size=cell_size, cols=cols, rows=rows)

    normal = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=target_rect,
        fall_spawn_cells=set(),
        ambient_palette_key=None,
        wall_rubble_ratio=0.5,
    )
    with_fall_spawn = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=target_rect,
        fall_spawn_cells=_build_fall_spawn_cells_for_rect(target_rect, cell_size=cell_size),
        ambient_palette_key=None,
        wall_rubble_ratio=0.5,
    )

    crop_w = max(8, int(round(normal.get_width() / 1.3)))
    crop_h = max(8, int(round(normal.get_height() / 1.3)))
    crop_rect = pygame.Rect(0, 0, crop_w, crop_h)
    crop_rect.center = normal.get_rect().center
    normal = normal.subsurface(crop_rect).copy()
    with_fall_spawn = with_fall_spawn.subsurface(crop_rect).copy()

    pygame.font.init()
    font = pygame.font.Font(None, 24)
    label_color = (220, 220, 220)
    bg = (24, 24, 24, 255)
    panel = (38, 38, 38, 255)

    margin = 12
    gap = 10
    label_h = 22
    width = margin * 2 + normal.get_width() * 2 + gap
    height = margin * 2 + label_h + normal.get_height()
    out = pygame.Surface((width, height), pygame.SRCALPHA)
    out.fill(bg)

    left_x = margin
    right_x = margin + normal.get_width() + gap
    image_y = margin + label_h

    pygame.draw.rect(
        out,
        panel,
        pygame.Rect(left_x - 1, image_y - 1, normal.get_width() + 2, normal.get_height() + 2),
        width=1,
    )
    pygame.draw.rect(
        out,
        panel,
        pygame.Rect(
            right_x - 1,
            image_y - 1,
            with_fall_spawn.get_width() + 2,
            with_fall_spawn.get_height() + 2,
        ),
        width=1,
    )

    out.blit(normal, (left_x, image_y))
    out.blit(with_fall_spawn, (right_x, image_y))

    out.blit(font.render("Normal Floor", True, label_color), (left_x, margin))
    out.blit(font.render("Fall Spawn + Floor", True, label_color), (right_x, margin))
    return out


def _draw_t_screw(
    target: pygame.Surface,
    *,
    x: int,
    y: int,
    color: tuple[int, int, int, int],
    orientation: int,
) -> None:
    direction = orientation % 4
    if direction == 0:  # up
        pygame.draw.line(target, color, (x - 2, y - 2), (x + 2, y - 2), width=1)
        pygame.draw.line(target, color, (x, y - 2), (x, y + 2), width=1)
    elif direction == 1:  # right
        pygame.draw.line(target, color, (x + 2, y - 2), (x + 2, y + 2), width=1)
        pygame.draw.line(target, color, (x - 2, y), (x + 2, y), width=1)
    elif direction == 2:  # down
        pygame.draw.line(target, color, (x - 2, y + 2), (x + 2, y + 2), width=1)
        pygame.draw.line(target, color, (x, y - 2), (x, y + 2), width=1)
    else:  # left
        pygame.draw.line(target, color, (x - 2, y - 2), (x - 2, y + 2), width=1)
        pygame.draw.line(target, color, (x - 2, y), (x + 2, y), width=1)


def _render_floor_ruin_decorations_sample(*, cell_size: int) -> pygame.Surface:
    cols, rows = _studio_grid_size(cell_size)
    cell_x = cols // 2
    cell_y = rows // 2
    target_rect = pygame.Rect(
        max(0, cell_x - 2) * cell_size,
        max(0, cell_y - 2) * cell_size,
        cell_size * 4,
        cell_size * 4,
    )
    surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=target_rect,
        ambient_palette_key=None,
        wall_rubble_ratio=0.0,
    )
    rng = random.Random(20260301)
    palette = get_environment_palette(None)
    floor = palette.floor_primary
    wall = palette.inner_wall

    w, h = surface.get_size()
    pad = max(6, int(round(min(w, h) * 0.08)))
    draw_rect = pygame.Rect(pad, pad, max(8, w - pad * 2), max(8, h - pad * 2))

    dark_dust = (
        max(0, floor[0] - 26),
        max(0, floor[1] - 26),
        max(0, floor[2] - 26),
        44,
    )
    light_dust = (
        min(255, floor[0] + 12),
        min(255, floor[1] + 12),
        min(255, floor[2] + 12),
        34,
    )
    for _ in range(10):
        px = rng.randrange(draw_rect.left, draw_rect.right)
        py = rng.randrange(draw_rect.top, draw_rect.bottom)
        surface.set_at((px, py), dark_dust if rng.random() < 0.68 else light_dust)

    for _ in range(3):
        cx = rng.randrange(draw_rect.left + 4, draw_rect.right - 4)
        cy = rng.randrange(draw_rect.top + 4, draw_rect.bottom - 4)
        chip_color = (
            max(0, int(wall[0] * rng.uniform(0.70, 0.90))),
            max(0, int(wall[1] * rng.uniform(0.70, 0.90))),
            max(0, int(wall[2] * rng.uniform(0.70, 0.90))),
            140,
        )
        base = rng.random() * math.tau
        angles = [
            base,
            base + rng.uniform(0.85, 2.15),
            base + rng.uniform(2.2, 4.7),
        ]
        radii = [rng.uniform(2.2, 5.2), rng.uniform(1.7, 4.9), rng.uniform(2.5, 5.8)]
        points = [
            (
                int(round(cx + math.cos(angle) * radius)),
                int(round(cy + math.sin(angle) * radius)),
            )
            for angle, radius in zip(angles, radii)
        ]
        if len({points[0], points[1], points[2]}) == 3:
            pygame.draw.polygon(surface, chip_color, points)

    screw_color = (140, 148, 160, 196)
    for i in range(2):
        sx = rng.randrange(draw_rect.left + 4, draw_rect.right - 4)
        sy = rng.randrange(draw_rect.top + 4, draw_rect.bottom - 4)
        _draw_t_screw(surface, x=sx, y=sy, color=screw_color, orientation=i + rng.randrange(0, 4))

    return surface


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
    tracker.refresh_image()
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
    wall_hugging.refresh_image()
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
    lineformer.refresh_image()
    lineformer_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=lineformer.rect,
        sprites=[lineformer],
        enable_shadows=True,
    )
    lineformer_path = out / "zombie-lineformer.png"
    _save_surface(lineformer_surface, lineformer_path, scale=output_scale)
    saved.append(lineformer_path)

    solitary = Zombie(center_x, center_y, kind=ZombieKind.SOLITARY)
    solitary.refresh_image()
    solitary_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=solitary.rect,
        sprites=[solitary],
        enable_shadows=True,
    )
    solitary_path = out / "zombie-solitary.png"
    _save_surface(solitary_surface, solitary_path, scale=output_scale)
    saved.append(solitary_path)

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

    zombie_dog_nimble = ZombieDog(center_x, center_y, variant="nimble")
    zombie_dog_nimble_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=zombie_dog_nimble.rect,
        sprites=[zombie_dog_nimble],
        enable_shadows=True,
    )
    zombie_dog_nimble_path = out / "zombie-dog-nimble.png"
    _save_surface(zombie_dog_nimble_surface, zombie_dog_nimble_path, scale=output_scale)
    saved.append(zombie_dog_nimble_path)

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

    reinforced_wall = ReinforcedWall(
        center_x - cell_size // 2,
        center_y - cell_size // 2,
        cell_size,
        cell_size,
        bevel_depth=INTERNAL_WALL_BEVEL_DEPTH,
        bevel_mask=(True, True, True, True),
        draw_bottom_side=True,
        bottom_side_ratio=0.1,
        side_shade_ratio=0.9,
        health=STEEL_BEAM_HEALTH,
    )
    reinforced_wall_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=reinforced_wall.rect,
        sprites=[reinforced_wall],
    )
    legacy_reinforced_wall_path = out / "wall-reinforced-concept.png"
    if legacy_reinforced_wall_path.exists():
        legacy_reinforced_wall_path.unlink()
    reinforced_wall_path = out / "wall-reinforced.png"
    _save_surface(reinforced_wall_surface, reinforced_wall_path, scale=output_scale)
    saved.append(reinforced_wall_path)

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

    fire_floor_rect = pygame.Rect(
        cell_x * cell_size,
        cell_y * cell_size,
        cell_size,
        cell_size,
    )
    fire_floor_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=fire_floor_rect,
        fire_floor_cells={(cell_x, cell_y)},
    )
    fire_floor_path = out / "fire-floor.png"
    _save_surface(fire_floor_surface, fire_floor_path, scale=output_scale)
    saved.append(fire_floor_path)

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

    puddle_cell_x = cell_x
    puddle_cell_y = cell_y
    puddle_rect = pygame.Rect(
        puddle_cell_x * cell_size,
        puddle_cell_y * cell_size,
        cell_size,
        cell_size,
    )
    puddle_padding = max(2, int(round(cell_size * 0.12)))
    puddle_rect = puddle_rect.inflate(puddle_padding * 2, puddle_padding * 2)
    puddle_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=puddle_rect,
        puddle_cells={(puddle_cell_x, puddle_cell_y)},
        ambient_palette_key=None,
    )
    puddle_path = out / "puddle.png"
    _save_surface(puddle_surface, puddle_path, scale=output_scale)
    saved.append(puddle_path)

    spiky_plant = SpikyPlant(center_x, center_y)
    spiky_plant_surface = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=spiky_plant.rect,
        sprites=[spiky_plant],
        enable_shadows=True,
    )
    spiky_plant_path = out / "spiky_plant.png"
    _save_surface(spiky_plant_surface, spiky_plant_path, scale=output_scale)
    saved.append(spiky_plant_path)

    floor_ruin_decorations = _render_floor_ruin_decorations_sample(cell_size=cell_size)
    floor_ruin_decorations_path = out / "floor-ruin-decorations.png"
    _save_surface(floor_ruin_decorations, floor_ruin_decorations_path, scale=output_scale)
    saved.append(floor_ruin_decorations_path)

    return saved
