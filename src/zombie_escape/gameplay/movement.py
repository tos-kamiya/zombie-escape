from __future__ import annotations

from typing import Any, Sequence

import math

import pygame

from ..gameplay_constants import (
    CAR_SPEED,
    PLAYER_SPEED,
    ZOMBIE_SEPARATION_DISTANCE,
    ZOMBIE_SPAWN_DELAY_MS,
    ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE,
)
from .constants import MAX_ZOMBIES
from ..models import GameData
from ..entities import Car, Player, Survivor, Wall, Zombie, walls_for_radius, WallIndex
from .spawn import spawn_weighted_zombie
from .survivors import update_survivors
from .utils import rect_visible_on_screen


def process_player_input(
    keys: Sequence[bool], player: Player, car: Car | None
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

    player_dx, player_dy, car_dx, car_dy = 0, 0, 0, 0

    if player.in_car and car and car.alive():
        target_speed = getattr(car, "speed", CAR_SPEED)
        move_len = math.hypot(dx_input, dy_input)
        if move_len > 0:
            car_dx, car_dy = (
                (dx_input / move_len) * target_speed,
                (dy_input / move_len) * target_speed,
            )
    elif not player.in_car:
        target_speed = PLAYER_SPEED
        move_len = math.hypot(dx_input, dy_input)
        if move_len > 0:
            player_dx, player_dy = (
                (dx_input / move_len) * target_speed,
                (dy_input / move_len) * target_speed,
            )

    return player_dx, player_dy, car_dx, car_dy


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

    all_walls = list(wall_group) if wall_index is None else None

    def walls_near(center: tuple[float, float], radius: float) -> list[Wall]:
        if wall_index is None:
            return all_walls or []
        return walls_for_radius(wall_index, center, radius, cell_size=game_data.cell_size)

    # Update player/car movement
    if player.in_car and active_car:
        car_walls = walls_near((active_car.x, active_car.y), 150.0)
        active_car.move(car_dx, car_dy, car_walls)
        player.rect.center = active_car.rect.center
        player.x, player.y = active_car.x, active_car.y
    elif not player.in_car:
        # Ensure player is in all_sprites if not in car
        if player not in all_sprites:
            all_sprites.add(player, layer=2)
        player.move(
            player_dx,
            player_dy,
            wall_group,
            wall_index=wall_index,
            cell_size=game_data.cell_size,
            level_width=game_data.level_width,
            level_height=game_data.level_height,
        )
    else:
        # Player flagged as in-car but car is gone; drop them back to foot control
        player.in_car = False

    # Update camera
    target_for_camera = active_car if player.in_car and active_car else player
    camera.update(target_for_camera)

    update_survivors(game_data, wall_index=wall_index)

    # Spawn new zombies if needed
    current_time = pygame.time.get_ticks()
    spawn_interval = max(1, getattr(stage, "spawn_interval_ms", ZOMBIE_SPAWN_DELAY_MS))
    spawn_blocked = stage.survival_stage and game_data.state.dawn_ready
    if (
        len(zombie_group) < MAX_ZOMBIES
        and not spawn_blocked
        and current_time - game_data.state.last_zombie_spawn_time > spawn_interval
    ):
        if spawn_weighted_zombie(game_data, config):
            game_data.state.last_zombie_spawn_time = current_time

    # Update zombies
    target_center = (
        active_car.rect.center if player.in_car and active_car else player.rect.center
    )
    buddies = [
        survivor
        for survivor in survivor_group
        if survivor.alive() and survivor.is_buddy and not survivor.rescued
    ]
    buddies_on_screen = [
        buddy for buddy in buddies if rect_visible_on_screen(camera, buddy.rect)
    ]

    survivors_on_screen: list[Survivor] = []
    if stage.rescue_stage:
        for survivor in survivor_group:
            if survivor.alive():
                if rect_visible_on_screen(camera, survivor.rect):
                    survivors_on_screen.append(survivor)

    zombies_sorted: list[Zombie] = sorted(list(zombie_group), key=lambda z: z.x)

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
            dist_to_target_sq = (target_center[0] - zombie.x) ** 2 + (
                target_center[1] - zombie.y
            ) ** 2
            nearest_buddy = min(
                buddies_on_screen,
                key=lambda buddy: (buddy.rect.centerx - zombie.x) ** 2
                + (buddy.rect.centery - zombie.y) ** 2,
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
                        key=lambda pos: (pos[0] - zombie.x) ** 2
                        + (pos[1] - zombie.y) ** 2,
                    )
        nearby_candidates = _nearby_zombies(idx)
        zombie_search_radius = ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE + zombie.radius + 120
        nearby_walls = walls_near((zombie.x, zombie.y), zombie_search_radius)
        zombie.update(
            target,
            nearby_walls,
            nearby_candidates,
            footprints=game_data.state.footprints,
            cell_size=game_data.cell_size,
            level_width=game_data.level_width,
            level_height=game_data.level_height,
            outer_wall_cells=game_data.layout.outer_wall_cells,
        )
