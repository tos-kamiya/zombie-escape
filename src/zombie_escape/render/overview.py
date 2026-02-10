from __future__ import annotations

import pygame
from pygame import sprite, surface

from ..colors import (
    BLACK,
    BLUE,
    FOOTPRINT_COLOR,
    YELLOW,
    WHITE,
    get_environment_palette,
)
from ..entities import (
    Car,
    Flashlight,
    FuelCan,
    Player,
    PatrolBot,
    Shoes,
    SteelBeam,
    Survivor,
    Wall,
    Zombie,
    ZombieDog,
)
from ..font_utils import load_font, render_text_surface
from ..localization import get_font_settings
from ..models import Footprint, GameData
from ..render_assets import RenderAssets, resolve_steel_beam_colors, resolve_wall_colors
from ..render_constants import MOVING_FLOOR_OVERVIEW_COLOR
from ..entities_constants import PATROL_BOT_COLLISION_RADIUS
from .hud import _get_fog_scale


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


def _draw_overview_tag(
    surface: surface.Surface,
    font: pygame.font.Font,
    text: str,
    item_rect: pygame.Rect,
    *,
    fg: tuple[int, int, int] = YELLOW,
    padding: tuple[int, int] = (4, 2),
    line_height_scale: float = 1.0,
) -> None:
    label = render_text_surface(
        font, text, fg, line_height_scale=line_height_scale
    )
    label_rect = label.get_rect()
    padded = label_rect.inflate(padding[0] * 2, padding[1] * 2)
    top_left = (item_rect.left, item_rect.top)
    bottom_left = (item_rect.left, item_rect.bottom - padded.height)
    if top_left[1] < 0 or top_left[1] + padded.height > surface.get_height():
        x, y = bottom_left
    else:
        x, y = top_left
    x = max(0, min(surface.get_width() - padded.width, x))
    y = max(0, min(surface.get_height() - padded.height, y))
    padded.topleft = (x, y)
    label_rect.center = padded.center
    surface.blit(label, label_rect)


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
    now_ms: int | None = None,
    fuel: FuelCan | None = None,
    flashlights: list[Flashlight] | None = None,
    shoes: list[Shoes] | None = None,
    buddies: list[Survivor] | None = None,
    survivors: list[Survivor] | None = None,
    patrol_bots: list[PatrolBot] | None = None,
    zombies: list[pygame.sprite.Sprite] | None = None,
    fall_spawn_cells: set[tuple[int, int]] | None = None,
    moving_floor_cells: dict[tuple[int, int], object] | None = None,
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
    cell_size = assets.internal_wall_grid_snap
    if cell_size > 0:
        for x, y in floor_cells:
            pygame.draw.rect(
                surface,
                floor_color,
                pygame.Rect(
                    x * cell_size,
                    y * cell_size,
                    cell_size,
                    cell_size,
                ),
            )
        if fall_spawn_cells:
            for x, y in fall_spawn_cells:
                pygame.draw.rect(
                    surface,
                    fall_floor,
                    pygame.Rect(
                        x * cell_size,
                        y * cell_size,
                        cell_size,
                        cell_size,
                    ),
                )
        if moving_floor_cells:
            for x, y in moving_floor_cells.keys():
                pygame.draw.rect(
                    surface,
                    MOVING_FLOOR_OVERVIEW_COLOR,
                    pygame.Rect(
                        x * cell_size,
                        y * cell_size,
                        cell_size,
                        cell_size,
                    ),
                )

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
    now = pygame.time.get_ticks() if now_ms is None else now_ms
    for fp in footprints:
        if not fp.visible:
            continue
        age = now - fp.time
        fade = 1 - (age / assets.footprint_lifetime_ms)
        fade = max(assets.footprint_min_fade, fade)
        color = tuple(max(0, min(255, int(c * fade))) for c in FOOTPRINT_COLOR)
        pygame.draw.circle(
            surface,
            color,
            (int(fp.pos[0]), int(fp.pos[1])),
            assets.footprint_overview_radius,
        )
    if fuel and fuel.alive():
        pygame.draw.rect(surface, YELLOW, fuel.rect, border_radius=3)
        pygame.draw.rect(surface, BLACK, fuel.rect, width=2, border_radius=3)
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
    if zombies:
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


def draw_debug_overview(
    assets: RenderAssets,
    screen: surface.Surface,
    overview_surface: surface.Surface,
    game_data: GameData,
    config: dict[str, object],
    *,
    screen_width: int,
    screen_height: int,
) -> None:
    cell_size = assets.internal_wall_grid_snap
    floor_cells: set[tuple[int, int]] = set()
    if cell_size > 0:
        floor_cells = compute_floor_cells(
            cols=max(0, game_data.layout.field_rect.width // cell_size),
            rows=max(0, game_data.layout.field_rect.height // cell_size),
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
        now_ms=game_data.state.elapsed_play_ms,
        fuel=game_data.fuel,
        flashlights=game_data.flashlights or [],
        shoes=game_data.shoes or [],
        buddies=[
            survivor
            for survivor in game_data.groups.survivor_group
            if survivor.alive() and survivor.is_buddy and not survivor.rescued
        ],
        survivors=list(game_data.groups.survivor_group),
        patrol_bots=list(game_data.groups.patrol_bot_group),
        zombies=list(game_data.groups.zombie_group),
        fall_spawn_cells=game_data.layout.fall_spawn_cells,
        moving_floor_cells=game_data.layout.moving_floor_cells,
        palette_key=game_data.state.ambient_palette_key,
    )
    fov_target = None
    if (
        game_data.player
        and game_data.player.in_car
        and game_data.car
        and game_data.car.alive()
    ):
        fov_target = game_data.car
    elif game_data.player:
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
    try:
        font_settings = get_font_settings()
        label_font = load_font(font_settings.resource, font_settings.scaled_size(11))
    except pygame.error as e:
        print(f"Error loading overview font: {e}")
        return
    scale_x = scaled_w / max(1, level_rect.width)
    scale_y = scaled_h / max(1, level_rect.height)

    def _scaled_rect(rect: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(
            int(scaled_rect.left + rect.left * scale_x),
            int(scaled_rect.top + rect.top * scale_y),
            max(1, int(rect.width * scale_x)),
            max(1, int(rect.height * scale_y)),
        )

    if game_data.car and game_data.car.alive():
        _draw_overview_tag(
            screen,
            label_font,
            "C",
            _scaled_rect(game_data.car.rect),
            line_height_scale=font_settings.line_height_scale,
        )
    for parked in game_data.waiting_cars:
        if parked.alive():
            _draw_overview_tag(
                screen,
                label_font,
                "C",
                _scaled_rect(parked.rect),
                line_height_scale=font_settings.line_height_scale,
            )
    if game_data.fuel and game_data.fuel.alive():
        _draw_overview_tag(
            screen,
            label_font,
            "F",
            _scaled_rect(game_data.fuel.rect),
            line_height_scale=font_settings.line_height_scale,
        )
    if game_data.flashlights:
        for flashlight in game_data.flashlights:
            if flashlight.alive():
                _draw_overview_tag(
                    screen,
                    label_font,
                    "L",
                    _scaled_rect(flashlight.rect),
                    line_height_scale=font_settings.line_height_scale,
                )
    if game_data.shoes:
        for item in game_data.shoes:
            if item.alive():
                _draw_overview_tag(
                    screen,
                    label_font,
                    "S",
                    _scaled_rect(item.rect),
                    line_height_scale=font_settings.line_height_scale,
                )
