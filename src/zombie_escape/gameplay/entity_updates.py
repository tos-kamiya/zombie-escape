from __future__ import annotations

import math
from typing import Any, Sequence

import pygame

from ..entities import (
    Car,
    Player,
    Survivor,
    Wall,
    Zombie,
)
from ..entities_constants import (
    HUMANOID_WALL_BUMP_FRAMES,
    PLAYER_SPEED,
    ZOMBIE_SEPARATION_DISTANCE,
    ZOMBIE_TRACKER_CROWD_BAND_WIDTH,
    ZOMBIE_TRACKER_GRID_CROWD_COUNT,
    ZOMBIE_WALL_HUG_SENSOR_DISTANCE,
)
from ..gameplay_constants import (
    SHOES_SPEED_MULTIPLIER_ONE,
    SHOES_SPEED_MULTIPLIER_TWO,
)
from ..models import FallingZombie, GameData
from ..rng import get_rng
from ..entities.movement_helpers import pitfall_target
from ..world_grid import WallIndex, apply_cell_edge_nudge, walls_for_radius
from .constants import MAX_ZOMBIES
from .spawn import spawn_weighted_zombie, update_falling_zombies
from .survivors import update_survivors
from .utils import rect_visible_on_screen

RNG = get_rng()


def process_player_input(
    keys: Sequence[bool],
    player: Player,
    car: Car | None,
    shoes_count: int = 0,
    pad_input: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float, float, float]:
    """Process keyboard input and return movement deltas."""
    dx_input, dy_input = 0, 0
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        dy_input -= 1
    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        dy_input += 1
    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        dx_input -= 1
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        dx_input += 1
    dx_input += pad_input[0]
    dy_input += pad_input[1]

    player.update_facing_from_input(dx_input, dy_input)

    player_dx, player_dy, car_dx, car_dy = 0, 0, 0, 0

    if player.in_car and car and car.alive():
        car.update_facing_from_input(dx_input, dy_input)
        target_speed = car.speed
        move_len = math.hypot(dx_input, dy_input)
        if move_len > 0:
            car_dx, car_dy = (
                (dx_input / move_len) * target_speed,
                (dy_input / move_len) * target_speed,
            )
    elif not player.in_car:
        target_speed = PLAYER_SPEED * _shoes_speed_multiplier(shoes_count)
        move_len = math.hypot(dx_input, dy_input)
        if move_len > 0:
            player_dx, player_dy = (
                (dx_input / move_len) * target_speed,
                (dy_input / move_len) * target_speed,
            )

    return player_dx, player_dy, car_dx, car_dy


def _shoes_speed_multiplier(shoes_count: int) -> float:
    count = max(0, int(shoes_count))
    if count >= 2:
        return SHOES_SPEED_MULTIPLIER_TWO
    if count == 1:
        return SHOES_SPEED_MULTIPLIER_ONE
    return 1.0




def update_entities(
    game_data: GameData,
    player_dx: float,
    player_dy: float,
    car_dx: float,
    car_dy: float,
    config: dict[str, Any],
    wall_index: WallIndex | None = None,
) -> None:
    """Update positions and states of game entities."""
    player = game_data.player
    assert player is not None
    car = game_data.car
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    zombie_group = game_data.groups.zombie_group
    survivor_group = game_data.groups.survivor_group
    camera = game_data.camera
    stage = game_data.stage
    active_car = car if car and car.alive() else None
    pitfall_cells = game_data.layout.pitfall_cells
    field_rect = game_data.layout.field_rect

    all_walls = list(wall_group) if wall_index is None else None

    def _walls_near(center: tuple[float, float], radius: float) -> list[Wall]:
        if wall_index is None:
            return all_walls or []
        return walls_for_radius(
            wall_index,
            center,
            radius,
            cell_size=game_data.cell_size,
            grid_cols=game_data.layout.grid_cols,
            grid_rows=game_data.layout.grid_rows,
        )

    # Update player/car movement
    if player.in_car and active_car:
        car_dx, car_dy = apply_cell_edge_nudge(
            active_car.x,
            active_car.y,
            car_dx,
            car_dy,
            layout=game_data.layout,
            cell_size=game_data.cell_size,
        )
        car_walls = _walls_near((active_car.x, active_car.y), 150.0)
        active_car.move(
            car_dx,
            car_dy,
            car_walls,
            walls_nearby=wall_index is not None,
            cell_size=game_data.cell_size,
            pitfall_cells=pitfall_cells,
        )
        if field_rect is not None:
            car_allow_rect = field_rect.inflate(active_car.rect.width, active_car.rect.height)
            clamped_rect = active_car.rect.clamp(car_allow_rect)
            if clamped_rect.topleft != active_car.rect.topleft:
                active_car.rect = clamped_rect
                active_car.x = float(active_car.rect.centerx)
                active_car.y = float(active_car.rect.centery)
        player.rect.center = active_car.rect.center
        player.x, player.y = active_car.x, active_car.y
    elif not player.in_car:
        # Ensure player is in all_sprites if not in car
        if player not in all_sprites:
            all_sprites.add(player, layer=2)
        player_dx, player_dy = apply_cell_edge_nudge(
            player.x,
            player.y,
            player_dx,
            player_dy,
            layout=game_data.layout,
            cell_size=game_data.cell_size,
        )
        player.move(
            player_dx,
            player_dy,
            wall_group,
            wall_index=wall_index,
            cell_size=game_data.cell_size,
            layout=game_data.layout,
        )
    else:
        # Player flagged as in-car but car is gone; drop them back to foot control
        player.in_car = False

    # Update camera
    target_for_camera = active_car if player.in_car and active_car else player
    camera.update(target_for_camera)

    if player.inner_wall_hit and player.inner_wall_cell is not None:
        game_data.state.player_wall_target_cell = player.inner_wall_cell
        game_data.state.player_wall_target_ttl = HUMANOID_WALL_BUMP_FRAMES
    elif game_data.state.player_wall_target_ttl > 0:
        game_data.state.player_wall_target_ttl -= 1
        if game_data.state.player_wall_target_ttl <= 0:
            game_data.state.player_wall_target_cell = None

    wall_target_cell = game_data.state.player_wall_target_cell if game_data.state.player_wall_target_ttl > 0 else None

    update_survivors(
        game_data,
        wall_index=wall_index,
        wall_target_cell=wall_target_cell,
    )
    update_falling_zombies(game_data, config)

    # Spawn new zombies if needed
    current_time = pygame.time.get_ticks()
    spawn_interval = max(1, stage.spawn_interval_ms)
    spawn_blocked = stage.endurance_stage and game_data.state.dawn_ready
    if (
        len(zombie_group) < MAX_ZOMBIES
        and not spawn_blocked
        and current_time - game_data.state.last_zombie_spawn_time > spawn_interval
    ):
        if spawn_weighted_zombie(game_data, config):
            game_data.state.last_zombie_spawn_time = current_time

    # Update zombies
    target_center = active_car.rect.center if player.in_car and active_car else player.rect.center
    buddies = [
        survivor for survivor in survivor_group if survivor.alive() and survivor.is_buddy and not survivor.rescued
    ]
    buddies_on_screen = [buddy for buddy in buddies if rect_visible_on_screen(camera, buddy.rect)]

    survivors_on_screen: list[Survivor] = []
    if stage.rescue_stage:
        for survivor in survivor_group:
            if survivor.alive():
                if rect_visible_on_screen(camera, survivor.rect):
                    survivors_on_screen.append(survivor)

    zombies_sorted: list[Zombie] = sorted(list(zombie_group), key=lambda z: z.x)

    tracker_buckets: dict[tuple[int, int, int], list[Zombie]] = {}
    tracker_cell_size = ZOMBIE_TRACKER_CROWD_BAND_WIDTH
    angle_step = math.pi / 4.0
    for zombie in zombies_sorted:
        if not zombie.alive() or not zombie.tracker:
            continue
        zombie.tracker_force_wander = False
        dx = zombie.last_move_dx
        dy = zombie.last_move_dy
        if abs(dx) <= 0.001 and abs(dy) <= 0.001:
            continue
        angle = math.atan2(dy, dx)
        angle_bin = int(round(angle / angle_step)) % 8
        cell_x = int(zombie.x // tracker_cell_size)
        cell_y = int(zombie.y // tracker_cell_size)
        tracker_buckets.setdefault((cell_x, cell_y, angle_bin), []).append(zombie)

    for bucket in tracker_buckets.values():
        if len(bucket) < ZOMBIE_TRACKER_GRID_CROWD_COUNT:
            continue
        RNG.choice(bucket).tracker_force_wander = True

    def _nearby_zombies(index: int) -> list[Zombie]:
        center = zombies_sorted[index]
        neighbors: list[Zombie] = []
        search_radius = ZOMBIE_SEPARATION_DISTANCE + PLAYER_SPEED
        for left in range(index - 1, -1, -1):
            other = zombies_sorted[left]
            if center.x - other.x > search_radius:
                break
            if other.alive():
                neighbors.append(other)
        for right in range(index + 1, len(zombies_sorted)):
            other = zombies_sorted[right]
            if other.x - center.x > search_radius:
                break
            if other.alive():
                neighbors.append(other)
        return neighbors

    for idx, zombie in enumerate(zombies_sorted):
        target = target_center
        if buddies_on_screen:
            dist_to_target_sq = (target_center[0] - zombie.x) ** 2 + (target_center[1] - zombie.y) ** 2
            nearest_buddy = min(
                buddies_on_screen,
                key=lambda buddy: (buddy.rect.centerx - zombie.x) ** 2 + (buddy.rect.centery - zombie.y) ** 2,
            )
            dist_to_buddy_sq = (nearest_buddy.rect.centerx - zombie.x) ** 2 + (
                nearest_buddy.rect.centery - zombie.y
            ) ** 2
            if dist_to_buddy_sq < dist_to_target_sq:
                target = nearest_buddy.rect.center

        if stage.rescue_stage:
            zombie_on_screen = rect_visible_on_screen(camera, zombie.rect)
            if zombie_on_screen:
                candidate_positions: list[tuple[int, int]] = []
                for survivor in survivors_on_screen:
                    candidate_positions.append(survivor.rect.center)
                for buddy in buddies_on_screen:
                    candidate_positions.append(buddy.rect.center)
                candidate_positions.append(player.rect.center)
                if candidate_positions:
                    target = min(
                        candidate_positions,
                        key=lambda pos: (pos[0] - zombie.x) ** 2 + (pos[1] - zombie.y) ** 2,
                    )
        nearby_candidates = _nearby_zombies(idx)
        zombie_search_radius = ZOMBIE_WALL_HUG_SENSOR_DISTANCE + zombie.radius + 120
        nearby_walls = _walls_near((zombie.x, zombie.y), zombie_search_radius)
        zombie.update(
            target,
            nearby_walls,
            nearby_candidates,
            footprints=game_data.state.footprints,
            cell_size=game_data.cell_size,
            layout=game_data.layout,
        )

        # Check zombie pitfall
        pull_dist = zombie.radius * 0.5
        pitfall_target_pos = pitfall_target(
            x=zombie.x,
            y=zombie.y,
            cell_size=game_data.cell_size,
            pitfall_cells=pitfall_cells,
            pull_distance=pull_dist,
        )
        if pitfall_target_pos is not None:
            zombie.kill()
            fall = FallingZombie(
                start_pos=(int(zombie.x), int(zombie.y)),
                target_pos=pitfall_target_pos,
                started_at_ms=game_data.state.elapsed_play_ms,
                pre_fx_ms=0,
                fall_duration_ms=500,
                dust_duration_ms=0,
                tracker=zombie.tracker,
                wall_hugging=zombie.wall_hugging,
                mode="pitfall",
            )
            game_data.state.falling_zombies.append(fall)
