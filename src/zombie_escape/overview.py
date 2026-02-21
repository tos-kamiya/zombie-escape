from __future__ import annotations

from typing import TYPE_CHECKING

import pygame
from pygame import sprite, surface

from .colors import (
    BLACK,
    BLUE,
    FOOTPRINT_COLOR,
    LIGHT_GRAY,
    RED,
    YELLOW,
    WHITE,
    get_environment_palette,
)
from .entities import (
    Car,
    EmptyFuelCan,
    Flashlight,
    FuelCan,
    FuelStation,
    Player,
    PatrolBot,
    Shoes,
    SpikyPlant,
    SteelBeam,
    Survivor,
    TrappedZombie,
    Wall,
    Zombie,
    ZombieDog,
)
from .models import Footprint, GameData
from .render_assets import RenderAssets, resolve_steel_beam_colors, resolve_wall_colors
from .render_constants import (
    FIRE_FLOOR_FLAME_COLORS,
    LINEFORMER_MARKER_OVERVIEW_COLOR,
    MOVING_FLOOR_OVERVIEW_COLOR,
    TRAPPED_ZOMBIE_OVERVIEW_COLOR,
)
from .entities_constants import PATROL_BOT_COLLISION_RADIUS
from .render.hud import _draw_status_bar, _get_fog_scale
from .render.puddle import get_puddle_wave_color

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .gameplay.lineformer_trains import LineformerTrainManager


def compute_floor_cells(
    *,
    cols: int,
    rows: int,
    wall_cells: set[tuple[int, int]],
    outer_wall_cells: set[tuple[int, int]],
    pitfall_cells: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """Return floor cells for the minimap base pass."""
    # The layout wall sets are updated when walls are destroyed, so removing
    # those cells here makes the minimap treat destroyed walls as floor.
    blocked = wall_cells | outer_wall_cells | pitfall_cells
    return {(x, y) for y in range(rows) for x in range(cols) if (x, y) not in blocked}


def _draw_spiky_plant_spike_mark(
    surface: surface.Surface,
    center: tuple[int, int],
    radius: int,
) -> None:
    body_fill_color = (64, 132, 64)
    body_outline_color = (90, 180, 90)
    spike_color = (90, 180, 90)
    body_radius = max(2, radius - 2)
    pygame.draw.circle(surface, body_fill_color, center, body_radius)
    pygame.draw.circle(surface, body_outline_color, center, body_radius, width=1)
    inner = max(1, radius - 2)
    outer = max(inner + 1, radius + 1)
    for i in range(8):
        angle = i * (360 / 8)
        direction = pygame.Vector2(1, 0).rotate(angle)
        start = (
            int(center[0] + direction.x * inner),
            int(center[1] + direction.y * inner),
        )
        end = (
            int(center[0] + direction.x * outer),
            int(center[1] + direction.y * outer),
        )
        pygame.draw.line(surface, spike_color, start, end, width=2)


def _draw_overview_floor_layers(
    surface: surface.Surface,
    *,
    cell_size: int,
    floor_cells: set[tuple[int, int]],
    floor_color: tuple[int, int, int],
    fall_floor: tuple[int, int, int],
    fall_spawn_cells: set[tuple[int, int]] | None,
    moving_floor_cells: dict[tuple[int, int], object] | None,
    fire_floor_cells: set[tuple[int, int]] | None,
    puddle_cells: set[tuple[int, int]] | None,
    zombie_contaminated_cells: set[tuple[int, int]] | None,
) -> None:
    if cell_size <= 0:
        return

    def _cell_rect(x: int, y: int) -> pygame.Rect:
        return pygame.Rect(x * cell_size, y * cell_size, cell_size, cell_size)

    for x, y in floor_cells:
        pygame.draw.rect(surface, floor_color, _cell_rect(x, y))
    if fall_spawn_cells:
        for x, y in fall_spawn_cells:
            pygame.draw.rect(surface, fall_floor, _cell_rect(x, y))
    if moving_floor_cells:
        for x, y in moving_floor_cells.keys():
            pygame.draw.rect(surface, MOVING_FLOOR_OVERVIEW_COLOR, _cell_rect(x, y))
    if fire_floor_cells:
        fire_diamond = tuple(
            max(0, int(channel * 0.35)) for channel in FIRE_FLOOR_FLAME_COLORS[0]
        )
        for x, y in fire_floor_cells:
            cell_rect = _cell_rect(x, y)
            inset = max(1, int(cell_size * 0.22))
            cx = cell_rect.centerx
            cy = cell_rect.centery
            diamond = [
                (cx, cell_rect.top + inset),
                (cell_rect.right - inset, cy),
                (cx, cell_rect.bottom - inset),
                (cell_rect.left + inset, cy),
            ]
            pygame.draw.polygon(surface, fire_diamond, diamond)
    if puddle_cells:
        puddle_color = get_puddle_wave_color(alpha=120)
        radius = max(1, int(cell_size * 0.28))
        for x, y in puddle_cells:
            cell_rect = _cell_rect(x, y)
            pygame.draw.circle(surface, puddle_color, cell_rect.center, radius, width=1)
    if zombie_contaminated_cells:
        for x, y in zombie_contaminated_cells:
            inset = max(1, int(cell_size * 0.05))
            cell_rect = _cell_rect(x, y)
            pygame.draw.rect(
                surface,
                RED,
                pygame.Rect(
                    cell_rect.x + inset,
                    cell_rect.y + inset,
                    max(1, cell_size - inset * 2),
                    max(1, cell_size - inset * 2),
                ),
                width=1,
            )


def _draw_overview_walls(
    surface: surface.Surface,
    *,
    wall_group: sprite.Group,
    floor_color: tuple[int, int, int],
    palette: object,
) -> None:
    for wall in wall_group:
        if wall.max_health > 0:
            health_ratio = max(0.0, min(1.0, wall.health / wall.max_health))
        else:
            health_ratio = 0.0
        if isinstance(wall, Wall):
            if health_ratio <= 0.0:
                pygame.draw.rect(surface, floor_color, wall.rect)
            else:
                fill_color, _ = resolve_wall_colors(
                    health_ratio=health_ratio,
                    palette_category=wall.palette_category,
                    palette=palette,
                )
                pygame.draw.rect(surface, fill_color, wall.rect)
        elif isinstance(wall, SteelBeam):
            if health_ratio <= 0.0:
                pygame.draw.rect(surface, floor_color, wall.rect)
            else:
                fill_color, _ = resolve_steel_beam_colors(
                    health_ratio=health_ratio,
                    palette=palette,
                )
                pygame.draw.rect(surface, fill_color, wall.rect)


def _draw_overview_footprints(
    surface: surface.Surface,
    *,
    assets: RenderAssets,
    footprints: list[Footprint],
    now_ms: int,
) -> None:
    for fp in footprints:
        if not fp.visible:
            continue
        age = now_ms - fp.time
        fade = 1 - (age / assets.footprint_lifetime_ms)
        fade = max(assets.footprint_min_fade, fade)
        color = tuple(max(0, min(255, int(c * fade))) for c in FOOTPRINT_COLOR)
        pygame.draw.circle(
            surface,
            color,
            (int(fp.pos[0]), int(fp.pos[1])),
            assets.footprint_overview_radius,
        )


def _draw_overview_items(
    surface: surface.Surface,
    *,
    fuel: FuelCan | None,
    empty_fuel_can: EmptyFuelCan | None,
    fuel_station: FuelStation | None,
    flashlights: list[Flashlight] | None,
    shoes: list[Shoes] | None,
) -> None:
    if fuel and fuel.alive():
        pygame.draw.rect(surface, YELLOW, fuel.rect, border_radius=3)
        pygame.draw.rect(surface, BLACK, fuel.rect, width=2, border_radius=3)
    if empty_fuel_can and empty_fuel_can.alive():
        pygame.draw.rect(surface, LIGHT_GRAY, empty_fuel_can.rect, border_radius=3)
        pygame.draw.rect(surface, BLACK, empty_fuel_can.rect, width=2, border_radius=3)
    if fuel_station and fuel_station.alive():
        pygame.draw.rect(surface, YELLOW, fuel_station.rect, border_radius=2)
        pygame.draw.rect(surface, BLACK, fuel_station.rect, width=2, border_radius=2)
    if flashlights:
        for flashlight in flashlights:
            if flashlight.alive():
                pygame.draw.rect(surface, YELLOW, flashlight.rect, border_radius=2)
                pygame.draw.rect(
                    surface, BLACK, flashlight.rect, width=2, border_radius=2
                )
    if shoes:
        for item in shoes:
            if item.alive():
                surface.blit(item.image, item.rect)


def _draw_overview_humanoids(
    surface: surface.Surface,
    *,
    assets: RenderAssets,
    player: Player | None,
    survivors: list[Survivor] | None,
    buddies: list[Survivor] | None,
    car: Car | None,
    waiting_cars: list[Car] | None,
    patrol_bots: list[PatrolBot] | None,
    spiky_plants: list[SpikyPlant] | None,
) -> None:
    if survivors:
        for survivor in survivors:
            if survivor.alive():
                pygame.draw.circle(
                    surface,
                    (220, 220, 255),
                    survivor.rect.center,
                    assets.player_radius * 2,
                )
    if player:
        pygame.draw.circle(surface, BLUE, player.rect.center, assets.player_radius * 2)
    if buddies:
        buddy_color = (0, 200, 70)
        for buddy in buddies:
            if buddy.alive() and not buddy.rescued:
                pygame.draw.circle(
                    surface, buddy_color, buddy.rect.center, assets.player_radius * 2
                )
    drawn_cars: list[Car] = []
    if car and car.alive():
        car_rect = car.image.get_rect(center=car.rect.center)
        surface.blit(car.image, car_rect)
        drawn_cars.append(car)
    if waiting_cars:
        for parked in waiting_cars:
            if not parked.alive() or parked in drawn_cars:
                continue
            parked_rect = parked.image.get_rect(center=parked.rect.center)
            surface.blit(parked.image, parked_rect)
    if patrol_bots:
        for bot in patrol_bots:
            if bot.alive():
                pygame.draw.circle(
                    surface,
                    (90, 45, 120),
                    bot.rect.center,
                    int(PATROL_BOT_COLLISION_RADIUS),
                )
    if spiky_plants:
        for hp in spiky_plants:
            if hp.alive():
                _draw_spiky_plant_spike_mark(
                    surface,
                    hp.rect.center,
                    max(2, int(hp.radius)),
                )


def _draw_overview_zombies(
    surface: surface.Surface,
    *,
    assets: RenderAssets,
    zombies: list[pygame.sprite.Sprite] | None,
    lineformer_trains: "LineformerTrainManager | None",
) -> None:
    if not zombies:
        return
    zombie_color = (200, 80, 80)
    zombie_radius = max(2, int(assets.player_radius * 1.2))
    for zombie in zombies:
        if not zombie.alive():
            continue
        if isinstance(zombie, (Zombie, ZombieDog)):
            pygame.draw.circle(
                surface,
                zombie_color,
                zombie.rect.center,
                zombie_radius,
            )
        elif isinstance(zombie, TrappedZombie):
            pygame.draw.circle(
                surface,
                TRAPPED_ZOMBIE_OVERVIEW_COLOR,
                zombie.rect.center,
                zombie_radius,
            )
    if lineformer_trains is not None:
        marker_radius = max(1, zombie_radius - 1)
        marker_draw_data = lineformer_trains.iter_marker_draw_data(zombies)
        for marker_x, marker_y, _ in marker_draw_data:
            pygame.draw.circle(
                surface,
                LINEFORMER_MARKER_OVERVIEW_COLOR,
                (int(marker_x), int(marker_y)),
                marker_radius,
            )


def draw_level_overview(
    assets: RenderAssets,
    surface: surface.Surface,
    wall_group: sprite.Group,
    floor_cells: set[tuple[int, int]],
    player: Player | None,
    car: Car | None,
    waiting_cars: list[Car] | None,
    footprints: list[Footprint],
    *,
    now_ms: int,
    fuel: FuelCan | None = None,
    empty_fuel_can: EmptyFuelCan | None = None,
    fuel_station: FuelStation | None = None,
    flashlights: list[Flashlight] | None = None,
    shoes: list[Shoes] | None = None,
    buddies: list[Survivor] | None = None,
    survivors: list[Survivor] | None = None,
    patrol_bots: list[PatrolBot] | None = None,
    spiky_plants: list[SpikyPlant] | None = None,
    zombies: list[pygame.sprite.Sprite] | None = None,
    lineformer_trains: "LineformerTrainManager | None" = None,
    fall_spawn_cells: set[tuple[int, int]] | None = None,
    moving_floor_cells: dict[tuple[int, int], object] | None = None,
    fire_floor_cells: set[tuple[int, int]] | None = None,
    puddle_cells: set[tuple[int, int]] | None = None,
    zombie_contaminated_cells: set[tuple[int, int]] | None = None,
    palette_key: str | None = None,
) -> None:
    palette = get_environment_palette(palette_key)
    base_floor = palette.floor_primary
    dark_floor = tuple(max(0, int(channel * 0.35)) for channel in base_floor)
    floor_color = tuple(max(0, int(channel * 0.65)) for channel in base_floor)
    fall_floor = tuple(
        max(0, int(channel * 0.55)) for channel in palette.fall_zone_primary
    )
    surface.fill(dark_floor)
    _draw_overview_floor_layers(
        surface,
        cell_size=assets.internal_wall_grid_snap,
        floor_cells=floor_cells,
        floor_color=floor_color,
        fall_floor=fall_floor,
        fall_spawn_cells=fall_spawn_cells,
        moving_floor_cells=moving_floor_cells,
        fire_floor_cells=fire_floor_cells,
        puddle_cells=puddle_cells,
        zombie_contaminated_cells=zombie_contaminated_cells,
    )
    _draw_overview_walls(
        surface,
        wall_group=wall_group,
        floor_color=floor_color,
        palette=palette,
    )
    _draw_overview_footprints(
        surface,
        assets=assets,
        footprints=footprints,
        now_ms=now_ms,
    )
    _draw_overview_items(
        surface,
        fuel=fuel,
        empty_fuel_can=empty_fuel_can,
        fuel_station=fuel_station,
        flashlights=flashlights,
        shoes=shoes,
    )
    _draw_overview_humanoids(
        surface,
        assets=assets,
        player=player,
        survivors=survivors,
        buddies=buddies,
        car=car,
        waiting_cars=waiting_cars,
        patrol_bots=patrol_bots,
        spiky_plants=spiky_plants,
    )
    _draw_overview_zombies(
        surface,
        assets=assets,
        zombies=zombies,
        lineformer_trains=lineformer_trains,
    )


def draw_debug_overview(
    assets: RenderAssets,
    screen: surface.Surface,
    overview_surface: surface.Surface,
    game_data: GameData,
    config: dict[str, object],
    *,
    screen_width: int,
    screen_height: int,
    show_debug_counts: bool = True,
) -> None:
    cell_size = assets.internal_wall_grid_snap
    floor_cells: set[tuple[int, int]] = set()
    if cell_size > 0:
        floor_cells = compute_floor_cells(
            cols=game_data.layout.grid_cols,
            rows=game_data.layout.grid_rows,
            wall_cells=game_data.layout.wall_cells,
            outer_wall_cells=game_data.layout.outer_wall_cells,
            pitfall_cells=game_data.layout.pitfall_cells,
        )
    footprints_enabled = bool(config.get("footprints", {}).get("enabled", True))
    footprints_to_draw = game_data.state.footprints if footprints_enabled else []
    draw_level_overview(
        assets,
        overview_surface,
        game_data.groups.wall_group,
        floor_cells,
        game_data.player,
        game_data.car,
        game_data.waiting_cars,
        footprints_to_draw,
        now_ms=game_data.state.clock.elapsed_ms,
        fuel=game_data.fuel,
        empty_fuel_can=game_data.empty_fuel_can,
        fuel_station=game_data.fuel_station,
        flashlights=game_data.flashlights or [],
        shoes=game_data.shoes or [],
        buddies=[
            survivor
            for survivor in game_data.groups.survivor_group
            if survivor.alive() and survivor.is_buddy and not survivor.rescued
        ],
        survivors=list(game_data.groups.survivor_group),
        patrol_bots=list(game_data.groups.patrol_bot_group),
        spiky_plants=list(game_data.spiky_plants.values()),
        zombies=list(game_data.groups.zombie_group),
        lineformer_trains=game_data.lineformer_trains,
        fall_spawn_cells=game_data.layout.fall_spawn_cells,
        moving_floor_cells=game_data.layout.moving_floor_cells,
        fire_floor_cells=game_data.layout.fire_floor_cells,
        puddle_cells=game_data.layout.puddle_cells,
        zombie_contaminated_cells=game_data.layout.zombie_contaminated_cells,
        palette_key=game_data.state.ambient_palette_key,
    )
    fov_target = None
    if game_data.player:
        mounted_vehicle = game_data.player.mounted_vehicle
        if mounted_vehicle is not None and mounted_vehicle.alive():
            fov_target = mounted_vehicle
        elif (
            game_data.player.in_car
            and game_data.car
            and game_data.car.alive()
        ):
            # Legacy fallback while call sites migrate from `in_car`.
            fov_target = game_data.car
    if fov_target is None and game_data.player:
        fov_target = game_data.player
    if fov_target:
        fov_scale = _get_fog_scale(assets, game_data.state.flashlight_count)
        fov_radius = max(1, int(assets.fov_radius * fov_scale))
        pygame.draw.circle(
            overview_surface,
            (255, 255, 120),
            fov_target.rect.center,
            fov_radius,
            width=2,
        )
    cam_offset = game_data.camera.camera
    camera_rect = pygame.Rect(
        -cam_offset.x,
        -cam_offset.y,
        screen_width,
        screen_height,
    )
    pygame.draw.rect(overview_surface, WHITE, camera_rect, width=1)
    level_rect = game_data.layout.field_rect
    level_aspect = level_rect.width / max(1, level_rect.height)
    screen_aspect = screen_width / max(1, screen_height)
    if level_aspect > screen_aspect:
        scaled_w = screen_width - 40
        scaled_h = int(scaled_w / level_aspect)
    else:
        scaled_h = screen_height - 40
        scaled_w = int(scaled_h * level_aspect)
    scaled_w = max(1, scaled_w)
    scaled_h = max(1, scaled_h)
    scaled_overview = pygame.transform.smoothscale(
        overview_surface, (scaled_w, scaled_h)
    )
    screen.fill(BLACK)
    scaled_rect = scaled_overview.get_rect(
        center=(screen_width // 2, screen_height // 2)
    )
    screen.blit(
        scaled_overview,
        scaled_rect,
    )
    _draw_status_bar(
        screen,
        assets,
        config,
        stage=game_data.stage,
        seed=game_data.state.seed,
        debug_mode=show_debug_counts,
        zombie_group=game_data.groups.zombie_group,
        lineformer_marker_count=game_data.lineformer_trains.total_marker_count(),
        falling_spawn_carry=game_data.state.falling_spawn_carry,
        show_fps=game_data.state.show_fps,
    )
