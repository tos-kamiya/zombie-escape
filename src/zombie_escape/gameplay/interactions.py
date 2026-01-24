from __future__ import annotations

from typing import Any

import pygame

from ..entities_constants import (
    CAR_HEIGHT,
    CAR_WIDTH,
    FLASHLIGHT_HEIGHT,
    FLASHLIGHT_WIDTH,
    FUEL_CAN_HEIGHT,
    FUEL_CAN_WIDTH,
    HUMANOID_RADIUS,
    SURVIVOR_APPROACH_RADIUS,
    SURVIVOR_MAX_SAFE_PASSENGERS,
)
from .constants import (
    CAR_ZOMBIE_DAMAGE,
    FUEL_HINT_DURATION_MS,
    SURVIVOR_OVERLOAD_DAMAGE_RATIO,
)
from ..localization import translate as tr
from ..models import GameData
from ..rng import get_rng
from ..entities import Car
from .footprints import get_shrunk_sprite
from .spawn import maintain_waiting_car_supply
from .survivors import (
    add_survivor_message,
    apply_passenger_speed_penalty,
    drop_survivors_from_car,
    handle_survivor_zombie_collisions,
    increase_survivor_capacity,
    respawn_buddies_near_player,
)
from .utils import rect_visible_on_screen
from .ambient import sync_ambient_palette_with_flashlights


def _interaction_radius(width: float, height: float) -> float:
    """Approximate interaction reach for a humanoid and an object."""
    return HUMANOID_RADIUS + (width + height) / 4

RNG = get_rng()


def check_interactions(game_data: GameData, config: dict[str, Any]) -> None:
    """Check and handle interactions between entities."""
    player = game_data.player
    assert player is not None
    car = game_data.car
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites
    survivor_group = game_data.groups.survivor_group
    state = game_data.state
    walkable_cells = game_data.layout.walkable_cells
    outside_rects = game_data.layout.outside_rects
    fuel = game_data.fuel
    flashlights = game_data.flashlights or []
    camera = game_data.camera
    stage = game_data.stage
    maintain_waiting_car_supply(game_data)
    active_car = car if car and car.alive() else None
    waiting_cars = game_data.waiting_cars
    shrunk_car = get_shrunk_sprite(active_car, 0.8) if active_car else None

    car_interaction_radius = _interaction_radius(CAR_WIDTH, CAR_HEIGHT)
    fuel_interaction_radius = _interaction_radius(FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT)
    flashlight_interaction_radius = _interaction_radius(
        FLASHLIGHT_WIDTH, FLASHLIGHT_HEIGHT
    )

    def _player_near_point(point: tuple[float, float], radius: float) -> bool:
        dx = point[0] - player.x
        dy = point[1] - player.y
        return dx * dx + dy * dy <= radius * radius

    def _player_near_sprite(
        sprite_obj: pygame.sprite.Sprite | None, radius: float
    ) -> bool:
        return bool(
            sprite_obj
            and sprite_obj.alive()
            and _player_near_point(sprite_obj.rect.center, radius)
        )

    def _player_near_car(car_obj: Car | None) -> bool:
        return _player_near_sprite(car_obj, car_interaction_radius)

    # Fuel pickup
    if fuel and fuel.alive() and not state.has_fuel and not player.in_car:
        if _player_near_point(fuel.rect.center, fuel_interaction_radius):
            state.has_fuel = True
            state.fuel_message_until = 0
            state.hint_expires_at = 0
            state.hint_target_type = None
            fuel.kill()
            game_data.fuel = None
            print("Fuel acquired!")

    # Flashlight pickup
    if not player.in_car:
        for flashlight in list(flashlights):
            if not flashlight.alive():
                continue
            if _player_near_point(
                flashlight.rect.center, flashlight_interaction_radius
            ):
                state.flashlight_count += 1
                state.hint_expires_at = 0
                state.hint_target_type = None
                flashlight.kill()
                try:
                    flashlights.remove(flashlight)
                except ValueError:
                    pass
                print("Flashlight acquired!")
                break

    sync_ambient_palette_with_flashlights(game_data)

    buddies = [
        survivor
        for survivor in survivor_group
        if survivor.alive() and survivor.is_buddy and not survivor.rescued
    ]

    # Buddy interactions (Stage 3)
    if stage.buddy_required_count > 0 and buddies:
        for buddy in list(buddies):
            if not buddy.alive():
                continue
            buddy_on_screen = rect_visible_on_screen(camera, buddy.rect)
            if not player.in_car:
                dist_to_player_sq = (player.x - buddy.x) ** 2 + (
                    player.y - buddy.y
                ) ** 2
                if (
                    dist_to_player_sq
                    <= SURVIVOR_APPROACH_RADIUS * SURVIVOR_APPROACH_RADIUS
                ):
                    buddy.set_following()
            elif player.in_car and active_car and shrunk_car:
                g = pygame.sprite.Group()
                g.add(buddy)
                if pygame.sprite.spritecollide(
                    shrunk_car, g, False, pygame.sprite.collide_circle
                ):
                    prospective_passengers = state.survivors_onboard + 1
                    capacity_limit = state.survivor_capacity
                    if prospective_passengers > capacity_limit:
                        overload_damage = max(
                            1,
                            int(active_car.max_health * SURVIVOR_OVERLOAD_DAMAGE_RATIO),
                        )
                        add_survivor_message(game_data, tr("survivors.too_many_aboard"))
                        active_car._take_damage(overload_damage)
                    state.buddy_onboard += 1
                    buddy.kill()
                    continue

            if buddy.alive() and pygame.sprite.spritecollide(
                buddy, zombie_group, False, pygame.sprite.collide_circle
            ):
                if buddy_on_screen:
                    state.game_over_message = tr("game_over.scream")
                    state.game_over = True
                    state.game_over_at = state.game_over_at or pygame.time.get_ticks()
                else:
                    if walkable_cells:
                        new_cell = RNG.choice(walkable_cells)
                        buddy.teleport(new_cell.center)
                    else:
                        buddy.teleport(
                            (game_data.level_width // 2, game_data.level_height // 2)
                        )
                    buddy.following = False

    # Player entering an active car already under control
    if (
        not player.in_car
        and _player_near_car(active_car)
        and active_car
        and active_car.health > 0
    ):
        if state.has_fuel:
            player.in_car = True
            all_sprites.remove(player)
            state.hint_expires_at = 0
            state.hint_target_type = None
            print("Player entered car!")
        else:
            if not stage.endurance_stage:
                now_ms = state.elapsed_play_ms
                state.fuel_message_until = now_ms + FUEL_HINT_DURATION_MS
                state.hint_target_type = "fuel"

    # Claim a waiting/parked car when the player finally reaches it
    if not player.in_car and not active_car and waiting_cars:
        claimed_car: Car | None = None
        for parked_car in waiting_cars:
            if _player_near_car(parked_car):
                claimed_car = parked_car
                break
        if claimed_car:
            if state.has_fuel:
                try:
                    game_data.waiting_cars.remove(claimed_car)
                except ValueError:
                    pass
                game_data.car = claimed_car
                active_car = claimed_car
                player.in_car = True
                all_sprites.remove(player)
                state.hint_expires_at = 0
                state.hint_target_type = None
                apply_passenger_speed_penalty(game_data)
                maintain_waiting_car_supply(game_data)
                print("Player claimed a waiting car!")
            else:
                if not stage.endurance_stage:
                    now_ms = state.elapsed_play_ms
                    state.fuel_message_until = now_ms + FUEL_HINT_DURATION_MS
                    state.hint_target_type = "fuel"

    # Bonus: collide a parked car while driving to repair/extend capabilities
    if player.in_car and active_car and shrunk_car and waiting_cars:
        waiting_group = pygame.sprite.Group(waiting_cars)
        collided_waiters = pygame.sprite.spritecollide(
            shrunk_car, waiting_group, False, pygame.sprite.collide_rect
        )
        if collided_waiters:
            removed_any = False
            capacity_increments = 0
            for parked in collided_waiters:
                if not parked.alive():
                    continue
                parked.kill()
                try:
                    game_data.waiting_cars.remove(parked)
                except ValueError:
                    pass
                active_car.health = active_car.max_health
                active_car._update_color()
                removed_any = True
                if stage.rescue_stage:
                    capacity_increments += 1
            if removed_any:
                if capacity_increments:
                    increase_survivor_capacity(game_data, capacity_increments)
                maintain_waiting_car_supply(game_data)

    # Car hitting zombies
    if player.in_car and active_car and active_car.health > 0 and shrunk_car:
        zombies_hit = pygame.sprite.spritecollide(shrunk_car, zombie_group, True)
        if zombies_hit:
            active_car._take_damage(CAR_ZOMBIE_DAMAGE * len(zombies_hit))

    if (
        stage.rescue_stage
        and player.in_car
        and active_car
        and shrunk_car
        and survivor_group
    ):
        boarded = pygame.sprite.spritecollide(
            shrunk_car, survivor_group, True, pygame.sprite.collide_circle
        )
        if boarded:
            state.survivors_onboard += len(boarded)
            apply_passenger_speed_penalty(game_data)
            capacity_limit = state.survivor_capacity
            if state.survivors_onboard > capacity_limit:
                overload_damage = max(
                    1,
                    int(active_car.max_health * SURVIVOR_OVERLOAD_DAMAGE_RATIO),
                )
                add_survivor_message(game_data, tr("survivors.too_many_aboard"))
                active_car._take_damage(overload_damage)

    if stage.rescue_stage:
        handle_survivor_zombie_collisions(game_data, config)

    # Handle car destruction
    if car and car.alive() and car.health <= 0:
        car_destroyed_pos = car.rect.center
        car.kill()
        if stage.rescue_stage:
            drop_survivors_from_car(game_data, car_destroyed_pos)
        if player.in_car:
            player.in_car = False
            player.x, player.y = car_destroyed_pos[0], car_destroyed_pos[1]
            player.rect.center = (int(player.x), int(player.y))
            if player not in all_sprites:
                all_sprites.add(player, layer=2)
            print("Car destroyed! Player ejected.")

        # Clear active car and let the player hunt for another waiting car.
        game_data.car = None
        state.survivor_capacity = SURVIVOR_MAX_SAFE_PASSENGERS
        apply_passenger_speed_penalty(game_data)

        # Bring back the buddies near the player after losing the car
        respawn_buddies_near_player(game_data)
        maintain_waiting_car_supply(game_data)

    # Player getting caught by zombies
    if not player.in_car and player in all_sprites:
        shrunk_player = get_shrunk_sprite(player, 0.8)
        collisions = pygame.sprite.spritecollide(
            shrunk_player, zombie_group, False, pygame.sprite.collide_circle
        )
        if any(not zombie.carbonized for zombie in collisions):
            if not state.game_over:
                state.game_over = True
                state.game_over_at = pygame.time.get_ticks()
                state.game_over_message = tr("game_over.scream")

    # Player escaping on foot after dawn (Stage 5)
    if (
        stage.endurance_stage
        and state.dawn_ready
        and not player.in_car
        and outside_rects
        and any(outside.collidepoint(player.rect.center) for outside in outside_rects)
    ):
        state.game_won = True

    # Player escaping the level
    if player.in_car and car and car.alive() and state.has_fuel:
        buddy_ready = True
        if stage.buddy_required_count > 0:
            buddy_ready = state.buddy_onboard >= stage.buddy_required_count
        if buddy_ready and any(
            outside.collidepoint(car.rect.center) for outside in outside_rects
        ):
            if stage.buddy_required_count > 0:
                state.buddy_rescued = min(
                    stage.buddy_required_count, state.buddy_onboard
                )
            if stage.rescue_stage and state.survivors_onboard:
                state.survivors_rescued += state.survivors_onboard
                state.survivors_onboard = 0
                apply_passenger_speed_penalty(game_data)
            state.game_won = True

    return None
