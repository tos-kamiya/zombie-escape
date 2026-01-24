from __future__ import annotations

from bisect import bisect_left
from typing import Any

import math

import pygame

from ..entities_constants import (
    BUDDY_RADIUS,
    CAR_SPEED,
    PLAYER_RADIUS,
    SURVIVOR_MAX_SAFE_PASSENGERS,
    SURVIVOR_MIN_SPEED_FACTOR,
    SURVIVOR_RADIUS,
    ZOMBIE_RADIUS,
)
from .constants import SURVIVOR_MESSAGE_DURATION_MS, SURVIVOR_SPEED_PENALTY_PER_PASSENGER
from ..localization import translate_dict, translate_list
from ..models import GameData, ProgressState
from ..rng import get_rng
from ..entities import Survivor, Zombie, spritecollideany_walls
from ..world_grid import WallIndex
from .spawn import _create_zombie
from .utils import find_nearby_offscreen_spawn_position, rect_visible_on_screen

RNG = get_rng()


def update_survivors(
    game_data: GameData, wall_index: WallIndex | None = None
) -> None:
    if not (game_data.stage.rescue_stage or game_data.stage.buddy_required_count > 0):
        return
    survivor_group = game_data.groups.survivor_group
    wall_group = game_data.groups.wall_group
    player = game_data.player
    car = game_data.car
    if not player:
        return
    target_rect = car.rect if player.in_car and car and car.alive() else player.rect
    target_pos = target_rect.center
    survivors = [s for s in survivor_group if s.alive()]
    for survivor in survivors:
        survivor.update_behavior(
            target_pos,
            wall_group,
            wall_index=wall_index,
            cell_size=game_data.cell_size,
            wall_cells=game_data.layout.wall_cells,
            bevel_corners=game_data.layout.bevel_corners,
            grid_cols=game_data.stage.grid_cols,
            grid_rows=game_data.stage.grid_rows,
            level_width=game_data.level_width,
            level_height=game_data.level_height,
        )

    # Gently prevent survivors from overlapping the player or each other
    def _separate_from_point(
        survivor: Survivor, point: tuple[float, float], min_dist: float
    ) -> None:
        dx = point[0] - survivor.x
        dy = point[1] - survivor.y
        dist = math.hypot(dx, dy)
        if dist == 0:
            angle = RNG.uniform(0, math.tau)
            dx, dy = math.cos(angle), math.sin(angle)
            dist = 1
        if dist < min_dist:
            push = min_dist - dist
            survivor.x -= (dx / dist) * push
            survivor.y -= (dy / dist) * push
            survivor.rect.center = (int(survivor.x), int(survivor.y))

    player_overlap = (SURVIVOR_RADIUS + PLAYER_RADIUS) * 1.05
    survivor_overlap = (SURVIVOR_RADIUS * 2) * 1.05

    player_point = (player.x, player.y)
    for survivor in survivors:
        _separate_from_point(survivor, player_point, player_overlap)

    survivors_with_x = sorted(
        ((survivor.x, survivor) for survivor in survivors), key=lambda item: item[0]
    )
    for i, (base_x, survivor) in enumerate(survivors_with_x):
        for other_base_x, other in survivors_with_x[i + 1 :]:
            if other_base_x - base_x > survivor_overlap:
                break
            dx = other.x - survivor.x
            dy = other.y - survivor.y
            dist = math.hypot(dx, dy)
            if dist == 0:
                angle = RNG.uniform(0, math.tau)
                dx, dy = math.cos(angle), math.sin(angle)
                dist = 1
            if dist < survivor_overlap:
                push = (survivor_overlap - dist) / 2
                offset_x = (dx / dist) * push
                offset_y = (dy / dist) * push
                survivor.x -= offset_x
                survivor.y -= offset_y
                other.x += offset_x
                other.y += offset_y
                survivor.rect.center = (int(survivor.x), int(survivor.y))
                other.rect.center = (int(other.x), int(other.y))


def calculate_car_speed_for_passengers(
    passengers: int, *, capacity: int = SURVIVOR_MAX_SAFE_PASSENGERS
) -> float:
    cap = max(1, capacity)
    load_ratio = max(0.0, passengers / cap)
    penalty = SURVIVOR_SPEED_PENALTY_PER_PASSENGER * load_ratio
    penalty = min(0.95, max(0.0, penalty))
    adjusted = CAR_SPEED * (1 - penalty)
    if passengers <= cap:
        return max(CAR_SPEED * SURVIVOR_MIN_SPEED_FACTOR, adjusted)

    overload = passengers - cap
    overload_factor = 1 / math.sqrt(overload + 1)
    overloaded_speed = CAR_SPEED * overload_factor
    return max(CAR_SPEED * SURVIVOR_MIN_SPEED_FACTOR, overloaded_speed)


def apply_passenger_speed_penalty(game_data: GameData) -> None:
    car = game_data.car
    if not car:
        return
    if not game_data.stage.rescue_stage:
        car.speed = CAR_SPEED
        return
    car.speed = calculate_car_speed_for_passengers(
        game_data.state.survivors_onboard,
        capacity=game_data.state.survivor_capacity,
    )


def increase_survivor_capacity(game_data: GameData, increments: int = 1) -> None:
    if increments <= 0:
        return
    if not game_data.stage.rescue_stage:
        return
    state = game_data.state
    state.survivor_capacity += increments * SURVIVOR_MAX_SAFE_PASSENGERS
    apply_passenger_speed_penalty(game_data)


def add_survivor_message(game_data: GameData, text: str) -> None:
    expires = pygame.time.get_ticks() + SURVIVOR_MESSAGE_DURATION_MS
    game_data.state.survivor_messages.append({"text": text, "expires_at": expires})


def _normalize_legacy_conversion_lines(data: dict[str, Any]) -> list[str]:
    numbered: list[tuple[int, str]] = []
    others: list[tuple[str, str]] = []
    for key, value in data.items():
        if not value:
            continue
        text = str(value)
        if isinstance(key, str) and key.startswith("line"):
            suffix = key[4:]
            if suffix.isdigit():
                numbered.append((int(suffix), text))
                continue
        others.append((str(key), text))
    numbered.sort(key=lambda item: item[0])
    others.sort(key=lambda item: item[0])
    return [text for _, text in numbered] + [text for _, text in others]


def _get_survivor_conversion_messages(stage_id: str) -> list[str]:
    key = f"stages.{stage_id}.survivor_conversion_messages"
    raw = translate_list(key)
    if raw:
        return [str(item) for item in raw if item]
    legacy = translate_dict(f"stages.{stage_id}.conversion_lines")
    if legacy:
        return _normalize_legacy_conversion_lines(legacy)
    return []


def random_survivor_conversion_line(stage_id: str) -> str:
    lines = _get_survivor_conversion_messages(stage_id)
    if not lines:
        return ""
    return RNG.choice(lines)


def cleanup_survivor_messages(state: ProgressState) -> None:
    now = pygame.time.get_ticks()
    state.survivor_messages = [
        msg for msg in state.survivor_messages if msg.get("expires_at", 0) > now
    ]


def drop_survivors_from_car(game_data: GameData, origin: tuple[int, int]) -> None:
    """Respawn boarded survivors back into the world after a crash."""
    count = game_data.state.survivors_onboard
    if count <= 0:
        return
    wall_group = game_data.groups.wall_group
    survivor_group = game_data.groups.survivor_group
    all_sprites = game_data.groups.all_sprites

    for survivor_idx in range(count):
        placed = False
        for attempt in range(6):
            angle = RNG.uniform(0, math.tau)
            dist = RNG.uniform(16, 40)
            pos = (
                origin[0] + math.cos(angle) * dist,
                origin[1] + math.sin(angle) * dist,
            )
            s = Survivor(*pos)
            if not spritecollideany_walls(s, wall_group):
                survivor_group.add(s)
                all_sprites.add(s, layer=1)
                placed = True
                break
        if not placed:
            s = Survivor(*origin)
            survivor_group.add(s)
            all_sprites.add(s, layer=1)

    game_data.state.survivors_onboard = 0
    apply_passenger_speed_penalty(game_data)


def handle_survivor_zombie_collisions(
    game_data: GameData, config: dict[str, Any]
) -> None:
    if not game_data.stage.rescue_stage:
        return
    survivor_group = game_data.groups.survivor_group
    if not survivor_group:
        return
    zombie_group = game_data.groups.zombie_group
    zombies = [z for z in zombie_group if z.alive()]
    if not zombies:
        return
    zombies.sort(key=lambda s: s.rect.centerx)
    zombie_xs = [z.rect.centerx for z in zombies]
    camera = game_data.camera
    walkable_cells = game_data.layout.walkable_cells

    for survivor in list(survivor_group):
        if not survivor.alive():
            continue
        survivor_radius = survivor.radius
        search_radius = survivor_radius + ZOMBIE_RADIUS
        search_radius_sq = search_radius * search_radius

        min_x = survivor.rect.centerx - search_radius
        max_x = survivor.rect.centerx + search_radius
        start_idx = bisect_left(zombie_xs, min_x)
        collided_zombie: Zombie | None = None
        for idx in range(start_idx, len(zombies)):
            zombie_x = zombie_xs[idx]
            if zombie_x > max_x:
                break
            zombie = zombies[idx]
            if not zombie.alive():
                continue
            dy = zombie.rect.centery - survivor.rect.centery
            if abs(dy) > search_radius:
                continue
            dx = zombie_x - survivor.rect.centerx
            if dx * dx + dy * dy <= search_radius_sq:
                collided_zombie = zombie
                break

        if collided_zombie is None:
            continue
        if not rect_visible_on_screen(camera, survivor.rect):
            spawn_pos = find_nearby_offscreen_spawn_position(
                walkable_cells,
                camera=camera,
            )
            survivor.teleport(spawn_pos)
            continue
        survivor.kill()
        line = random_survivor_conversion_line(game_data.stage.id)
        if line:
            add_survivor_message(game_data, line)
        new_zombie = _create_zombie(
            config,
            start_pos=survivor.rect.center,
            stage=game_data.stage,
            tracker=collided_zombie.tracker,
            wall_follower=collided_zombie.wall_follower,
        )
        zombie_group.add(new_zombie)
        game_data.groups.all_sprites.add(new_zombie, layer=1)
        insert_idx = bisect_left(zombie_xs, new_zombie.rect.centerx)
        zombie_xs.insert(insert_idx, new_zombie.rect.centerx)
        zombies.insert(insert_idx, new_zombie)


def respawn_buddies_near_player(game_data: GameData) -> None:
    """Bring back onboard buddies near the player after losing the car."""
    if game_data.stage.buddy_required_count <= 0:
        return
    count = game_data.state.buddy_onboard
    if count <= 0:
        return

    player = game_data.player
    assert player is not None
    wall_group = game_data.groups.wall_group
    camera = game_data.camera
    walkable_cells = game_data.layout.walkable_cells
    offsets = [
        (BUDDY_RADIUS * 3, 0),
        (-BUDDY_RADIUS * 3, 0),
        (0, BUDDY_RADIUS * 3),
        (0, -BUDDY_RADIUS * 3),
        (0, 0),
    ]
    for _ in range(count):
        if walkable_cells:
            spawn_pos = find_nearby_offscreen_spawn_position(
                walkable_cells,
                camera=camera,
            )
        else:
            spawn_pos = (int(player.x), int(player.y))
        for dx, dy in offsets:
            candidate = Survivor(player.x + dx, player.y + dy, is_buddy=True)
            if not spritecollideany_walls(candidate, wall_group):
                spawn_pos = (candidate.x, candidate.y)
                break

        buddy = Survivor(*spawn_pos, is_buddy=True)
        buddy.following = True
        game_data.groups.all_sprites.add(buddy, layer=2)
        game_data.groups.survivor_group.add(buddy)
    game_data.state.buddy_onboard = 0
