from __future__ import annotations

from typing import Any

import math

import pygame

from ..entities_constants import (
    BUDDY_FOLLOW_START_DISTANCE,
    BUDDY_FOLLOW_STOP_DISTANCE,
    CAR_HEIGHT,
    CAR_WALL_DAMAGE,
    CAR_WIDTH,
    EMPTY_FUEL_CAN_HEIGHT,
    EMPTY_FUEL_CAN_WIDTH,
    FLASHLIGHT_HEIGHT,
    FLASHLIGHT_WIDTH,
    FUEL_CAN_HEIGHT,
    FUEL_CAN_WIDTH,
    FUEL_STATION_HEIGHT,
    FUEL_STATION_WIDTH,
    HUMANOID_RADIUS,
    SHOES_HEIGHT,
    SHOES_WIDTH,
    SURVIVOR_MAX_SAFE_PASSENGERS,
)
from .constants import (
    FUEL_HINT_DURATION_MS,
    LAYER_PLAYERS,
    SURVIVOR_OVERLOAD_DAMAGE_RATIO,
)
from ..colors import BLUE, YELLOW
from ..localization import translate as tr
from ..models import FuelMode, FuelProgress, GameData
from ..rng import get_rng
from ..render_constants import BUDDY_COLOR
from ..screen_constants import FPS
from ..entities import Car
from ..entities.collisions import collide_circle_custom
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
from .utils import is_active_zombie_threat, is_entity_in_fov, rect_visible_on_screen
from .ambient import sync_ambient_palette_with_flashlights
from .constants import SCREAM_MESSAGE_DISPLAY_FRAMES
from .state import schedule_timed_message


def _interaction_radius(width: float, height: float) -> float:
    """Approximate interaction reach for a humanoid and an object."""
    return HUMANOID_RADIUS + (width + height) / 4


def _ms_to_frames(ms: int) -> int:
    if ms <= 0:
        return 0
    return max(1, int(round(ms / (1000 / max(1, FPS)))))


RNG = get_rng()

# --- Car vs zombie damage (interaction rules) ---
CAR_ZOMBIE_RAM_DAMAGE = 6
CAR_ZOMBIE_CONTACT_DAMAGE = 2
CAR_ZOMBIE_HIT_DAMAGE = 20


def _handle_fuel_pickup(
    *,
    game_data: GameData,
    player: pygame.sprite.Sprite,
    fuel: pygame.sprite.Sprite | None,
    fuel_interaction_radius: float,
    need_fuel_text: str,
    player_near_point: callable,
) -> None:
    state = game_data.state
    if not (
        fuel
        and fuel.alive()
        and state.fuel_progress != FuelProgress.FULL_CAN
        and not player.in_car
    ):
        return
    if not player_near_point(fuel.rect.center, fuel_interaction_radius):
        return
    state.fuel_progress = FuelProgress.FULL_CAN
    if state.timed_message == need_fuel_text:
        schedule_timed_message(state, None, duration_frames=0, now_ms=state.clock.elapsed_ms)
    state.hint_expires_at = 0
    state.hint_target_type = None
    fuel.kill()
    game_data.fuel = None
    print("Fuel acquired!")


def _handle_empty_fuel_can_pickup(
    *,
    game_data: GameData,
    player: pygame.sprite.Sprite,
    empty_fuel_can: pygame.sprite.Sprite | None,
    interaction_radius: float,
    player_near_point: callable,
) -> bool:
    state = game_data.state
    if not (
        empty_fuel_can
        and empty_fuel_can.alive()
        and state.fuel_progress == FuelProgress.NONE
        and not player.in_car
    ):
        return False
    if not player_near_point(empty_fuel_can.rect.center, interaction_radius):
        return False
    state.fuel_progress = FuelProgress.EMPTY_CAN
    state.hint_expires_at = 0
    state.hint_target_type = None
    empty_fuel_can.kill()
    game_data.empty_fuel_can = None
    print("Empty fuel can acquired!")
    return True


def _handle_fuel_station_refuel(
    *,
    game_data: GameData,
    player: pygame.sprite.Sprite,
    fuel_station: pygame.sprite.Sprite | None,
    interaction_radius: float,
    need_fuel_text: str,
    player_near_point: callable,
    ) -> bool:
    state = game_data.state
    if not (
        fuel_station
        and fuel_station.alive()
        and state.fuel_progress == FuelProgress.EMPTY_CAN
        and not player.in_car
    ):
        return False
    if not player_near_point(fuel_station.rect.center, interaction_radius):
        return False
    state.fuel_progress = FuelProgress.FULL_CAN
    if state.timed_message == need_fuel_text:
        schedule_timed_message(
            state, None, duration_frames=0, now_ms=state.clock.elapsed_ms
        )
    state.hint_expires_at = 0
    state.hint_target_type = None
    print("Fuel can filled at station!")
    return True


def _handle_fuel_station_without_can_hint(
    *,
    game_data: GameData,
    player: pygame.sprite.Sprite,
    fuel_station: pygame.sprite.Sprite | None,
    interaction_radius: float,
    need_empty_can_text: str,
    player_near_point: callable,
) -> None:
    state = game_data.state
    if not (
        fuel_station
        and fuel_station.alive()
        and state.fuel_progress == FuelProgress.NONE
        and not player.in_car
    ):
        return
    if not player_near_point(fuel_station.rect.center, interaction_radius):
        return
    schedule_timed_message(
        state,
        need_empty_can_text,
        duration_frames=_ms_to_frames(FUEL_HINT_DURATION_MS),
        clear_on_input=False,
        color=YELLOW,
        now_ms=state.clock.elapsed_ms,
    )
    state.hint_target_type = "empty_fuel_can"


def _handle_player_item_pickups(
    *,
    game_data: GameData,
    player: pygame.sprite.Sprite,
    flashlights: list[pygame.sprite.Sprite],
    shoes_list: list[pygame.sprite.Sprite],
    flashlight_interaction_radius: float,
    shoes_interaction_radius: float,
    player_near_point: callable,
) -> None:
    state = game_data.state
    if player.in_car:
        return
    for flashlight in list(flashlights):
        if not flashlight.alive():
            continue
        if not player_near_point(flashlight.rect.center, flashlight_interaction_radius):
            continue
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

    for shoes in list(shoes_list):
        if not shoes.alive():
            continue
        if not player_near_point(shoes.rect.center, shoes_interaction_radius):
            continue
        state.shoes_count += 1
        state.hint_expires_at = 0
        state.hint_target_type = None
        shoes.kill()
        try:
            shoes_list.remove(shoes)
        except ValueError:
            pass
        print("Shoes acquired!")
        break


def _board_survivors_if_colliding(
    *,
    game_data: GameData,
    player: pygame.sprite.Sprite,
    active_car: Car | None,
    shrunk_car: pygame.sprite.Sprite | None,
    survivor_group: pygame.sprite.Group,
    survivor_boarding_enabled: bool,
) -> None:
    if not (
        survivor_boarding_enabled
        and player.in_car
        and active_car
        and shrunk_car
        and survivor_group
    ):
        return
    state = game_data.state
    boarded_candidates = pygame.sprite.spritecollide(
        shrunk_car, survivor_group, False, collide_circle_custom
    )
    boarded = list(boarded_candidates)
    for survivor in boarded:
        survivor.kill()
    if not boarded:
        return
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


def _handle_car_destruction(
    *,
    game_data: GameData,
    player: pygame.sprite.Sprite,
    car: Car | None,
    all_sprites: pygame.sprite.LayeredUpdates,
    survivor_boarding_enabled: bool,
) -> None:
    state = game_data.state
    if not (car and car.alive() and car.health <= 0):
        return
    fell_into_pitfall = bool(getattr(car, "pending_pitfall_fall", False))
    car_destroyed_pos = car.rect.center
    eject_pos = getattr(car, "pitfall_eject_pos", None) or car_destroyed_pos
    car.kill()
    if survivor_boarding_enabled:
        drop_survivors_from_car(game_data, eject_pos)
    if player.in_car:
        player.in_car = False
        player.x, player.y = eject_pos[0], eject_pos[1]
        player.rect.center = (int(player.x), int(player.y))
        if player not in all_sprites:
            all_sprites.add(player, layer=LAYER_PLAYERS)
        if fell_into_pitfall:
            print("Car fell into pitfall! Player ejected.")
        else:
            print("Car destroyed! Player ejected.")

    # Clear active car and let the player hunt for another waiting car.
    game_data.car = None
    state.survivor_capacity = SURVIVOR_MAX_SAFE_PASSENGERS
    apply_passenger_speed_penalty(game_data)

    # Bring back the buddies near the player after losing the car
    respawn_buddies_near_player(game_data)
    maintain_waiting_car_supply(game_data)


def _handle_escape_conditions(
    *,
    game_data: GameData,
    player: pygame.sprite.Sprite,
    car: Car | None,
    outside_cells: set[tuple[int, int]],
    survivor_boarding_enabled: bool,
    rect_center_cell: callable,
) -> None:
    stage = game_data.stage
    state = game_data.state
    # Player escaping on foot after dawn (Stage 5)
    if (
        stage.endurance_stage
        and state.dawn_ready
        and not player.in_car
        and outside_cells
        and (player_cell := rect_center_cell(player.rect)) is not None
        and player_cell in outside_cells
    ):
        buddy_ready = True
        if stage.buddy_required_count > 0:
            buddy_ready = state.buddy_merged_count >= stage.buddy_required_count
        if buddy_ready:
            state.game_won = True

    # Player escaping the level
    if (
        player.in_car
        and car
        and car.alive()
        and state.fuel_progress == FuelProgress.FULL_CAN
    ):
        buddy_ready = True
        if stage.buddy_required_count > 0:
            buddy_ready = state.buddy_merged_count >= stage.buddy_required_count
        car_cell = rect_center_cell(car.rect)
        if buddy_ready and car_cell is not None and car_cell in outside_cells:
            if stage.buddy_required_count > 0:
                state.buddy_rescued = min(
                    stage.buddy_required_count, state.buddy_merged_count
                )
            if survivor_boarding_enabled and state.survivors_onboard:
                state.survivors_rescued += state.survivors_onboard
                state.survivors_onboard = 0
                apply_passenger_speed_penalty(game_data)
            state.game_won = True


def _handle_buddy_interactions(
    *,
    game_data: GameData,
    player: pygame.sprite.Sprite,
    active_car: Car | None,
    shrunk_car: pygame.sprite.Sprite | None,
    zombie_group: pygame.sprite.Group,
    survivor_group: pygame.sprite.Group,
    camera: Any,
    walkable_cells: list[tuple[int, int]],
    cell_center: callable,
    lineformer_trains: Any,
) -> None:
    stage = game_data.stage
    state = game_data.state
    buddies = [
        survivor
        for survivor in survivor_group
        if survivor.alive() and survivor.is_buddy and not survivor.rescued
    ]
    if stage.buddy_required_count > 0 and buddies:
        for buddy in list(buddies):
            if not buddy.alive():
                continue
            buddy_on_screen = rect_visible_on_screen(camera, buddy.rect)
            if not player.in_car:
                dist_to_player_sq = (player.x - buddy.x) ** 2 + (player.y - buddy.y) ** 2
                if buddy.following:
                    if (
                        dist_to_player_sq
                        >= BUDDY_FOLLOW_STOP_DISTANCE * BUDDY_FOLLOW_STOP_DISTANCE
                    ):
                        buddy.following = False
                elif (
                    dist_to_player_sq
                    <= BUDDY_FOLLOW_START_DISTANCE * BUDDY_FOLLOW_START_DISTANCE
                ):
                    buddy.set_following()
            elif player.in_car and active_car and shrunk_car:
                g = pygame.sprite.Group()
                g.add(buddy)
                if pygame.sprite.spritecollide(
                    shrunk_car, g, False, collide_circle_custom
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

            collisions: list[pygame.sprite.Sprite] = []
            if buddy.alive():
                collisions = pygame.sprite.spritecollide(
                    buddy, zombie_group, False, collide_circle_custom
                )
            now = state.clock.elapsed_ms
            marker_caught = lineformer_trains.any_marker_collides_circle(
                center=(buddy.x, buddy.y),
                radius=max(1.0, float(getattr(buddy, "collision_radius", HUMANOID_RADIUS))),
            )
            buddy_caught = any(
                is_active_zombie_threat(zombie, now_ms=now) for zombie in collisions
            ) or marker_caught
            if buddy.alive() and buddy_caught:
                if player.in_car and active_car:
                    fov_target = active_car
                else:
                    fov_target = player
                buddy_in_fov = is_entity_in_fov(
                    buddy.rect,
                    fov_target=fov_target,
                    flashlight_count=state.flashlight_count,
                )
                if buddy_on_screen and buddy_in_fov:
                    schedule_timed_message(
                        state,
                        tr("game_over.scream"),
                        duration_frames=SCREAM_MESSAGE_DISPLAY_FRAMES,
                        clear_on_input=False,
                        color=BUDDY_COLOR,
                        now_ms=now,
                    )
                    state.game_over = True
                    state.game_over_at = state.game_over_at or now
                else:
                    if walkable_cells:
                        new_cell = RNG.choice(walkable_cells)
                        buddy.teleport(cell_center(new_cell))
                    else:
                        buddy.teleport(game_data.layout.field_rect.center)
                    buddy.following = False

    if stage.buddy_required_count > 0:
        following_count = sum(1 for buddy in buddies if buddy.following)
        state.buddy_merged_count = state.buddy_onboard + following_count
    else:
        state.buddy_merged_count = 0


def check_interactions(game_data: GameData, config: dict[str, Any]) -> None:
    """Check and handle interactions between entities."""
    player = game_data.player
    assert player is not None
    car = game_data.car
    zombie_group = game_data.groups.zombie_group
    patrol_bot_group = game_data.groups.patrol_bot_group
    all_sprites = game_data.groups.all_sprites
    survivor_group = game_data.groups.survivor_group
    state = game_data.state
    walkable_cells = game_data.layout.walkable_cells
    outside_cells = game_data.layout.outside_cells
    fuel = game_data.fuel
    empty_fuel_can = game_data.empty_fuel_can
    fuel_station = game_data.fuel_station
    flashlights = game_data.flashlights or []
    shoes_list = game_data.shoes or []
    camera = game_data.camera
    stage = game_data.stage
    cell_size = game_data.cell_size
    need_fuel_text = tr("hud.need_fuel")
    need_empty_can_text = tr("hud.need_empty_fuel_can")
    survivor_boarding_enabled = (
        stage.survivor_rescue_stage or stage.survivor_spawn_rate > 0.0
    )
    maintain_waiting_car_supply(game_data)
    active_car = car if car and car.alive() else None
    waiting_cars = game_data.waiting_cars
    shrunk_car = get_shrunk_sprite(active_car, 0.8) if active_car else None

    car_interaction_radius = _interaction_radius(CAR_WIDTH, CAR_HEIGHT)
    fuel_interaction_radius = _interaction_radius(FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT)
    empty_fuel_can_interaction_radius = _interaction_radius(
        EMPTY_FUEL_CAN_WIDTH, EMPTY_FUEL_CAN_HEIGHT
    )
    fuel_station_interaction_radius = _interaction_radius(
        FUEL_STATION_WIDTH, FUEL_STATION_HEIGHT
    )
    flashlight_interaction_radius = _interaction_radius(
        FLASHLIGHT_WIDTH, FLASHLIGHT_HEIGHT
    )
    shoes_interaction_radius = _interaction_radius(SHOES_WIDTH, SHOES_HEIGHT)

    def _rect_center_cell(rect: pygame.Rect) -> tuple[int, int] | None:
        if cell_size <= 0:
            return None
        return (int(rect.centerx // cell_size), int(rect.centery // cell_size))

    def _cell_center(cell: tuple[int, int]) -> tuple[int, int]:
        return (
            int((cell[0] * cell_size) + (cell_size / 2)),
            int((cell[1] * cell_size) + (cell_size / 2)),
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

    if stage.fuel_mode == FuelMode.REFUEL_CHAIN:
        picked_empty_this_frame = _handle_empty_fuel_can_pickup(
            game_data=game_data,
            player=player,
            empty_fuel_can=empty_fuel_can,
            interaction_radius=empty_fuel_can_interaction_radius,
            player_near_point=_player_near_point,
        )
        if not picked_empty_this_frame:
            _handle_fuel_station_refuel(
                game_data=game_data,
                player=player,
                fuel_station=fuel_station,
                interaction_radius=fuel_station_interaction_radius,
                need_fuel_text=need_fuel_text,
                player_near_point=_player_near_point,
            )
            _handle_fuel_station_without_can_hint(
                game_data=game_data,
                player=player,
                fuel_station=fuel_station,
                interaction_radius=fuel_station_interaction_radius,
                need_empty_can_text=need_empty_can_text,
                player_near_point=_player_near_point,
            )
    else:
        _handle_fuel_pickup(
            game_data=game_data,
            player=player,
            fuel=fuel,
            fuel_interaction_radius=fuel_interaction_radius,
            need_fuel_text=need_fuel_text,
            player_near_point=_player_near_point,
        )
    _handle_player_item_pickups(
        game_data=game_data,
        player=player,
        flashlights=flashlights,
        shoes_list=shoes_list,
        flashlight_interaction_radius=flashlight_interaction_radius,
        shoes_interaction_radius=shoes_interaction_radius,
        player_near_point=_player_near_point,
    )

    sync_ambient_palette_with_flashlights(game_data)

    _handle_buddy_interactions(
        game_data=game_data,
        player=player,
        active_car=active_car,
        shrunk_car=shrunk_car,
        zombie_group=zombie_group,
        survivor_group=survivor_group,
        camera=camera,
        walkable_cells=walkable_cells,
        cell_center=_cell_center,
        lineformer_trains=game_data.lineformer_trains,
    )

    # Player entering an active car already under control
    if (
        not player.in_car
        and _player_near_car(active_car)
        and active_car
        and active_car.health > 0
    ):
        if state.fuel_progress >= FuelProgress.FULL_CAN:
            player.in_car = True
            all_sprites.remove(player)
            state.hint_expires_at = 0
            state.hint_target_type = None
            print("Player entered car!")
        else:
            if not stage.endurance_stage:
                schedule_timed_message(
                    state,
                    need_fuel_text,
                    duration_frames=_ms_to_frames(FUEL_HINT_DURATION_MS),
                    clear_on_input=False,
                    color=YELLOW,
                    now_ms=state.clock.elapsed_ms,
                )
                if stage.fuel_mode == FuelMode.REFUEL_CHAIN:
                    state.hint_target_type = (
                        "fuel_station"
                        if state.fuel_progress == FuelProgress.EMPTY_CAN
                        else "empty_fuel_can"
                    )
                else:
                    state.hint_target_type = "fuel"

    # Claim a waiting/parked car when the player finally reaches it
    if not player.in_car and not active_car and waiting_cars:
        claimed_car: Car | None = None
        for parked_car in waiting_cars:
            if _player_near_car(parked_car):
                claimed_car = parked_car
                break
        if claimed_car:
            if state.fuel_progress >= FuelProgress.FULL_CAN:
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
                    schedule_timed_message(
                        state,
                        need_fuel_text,
                        duration_frames=_ms_to_frames(FUEL_HINT_DURATION_MS),
                        clear_on_input=False,
                        color=YELLOW,
                        now_ms=state.clock.elapsed_ms,
                    )
                    if stage.fuel_mode == FuelMode.REFUEL_CHAIN:
                        state.hint_target_type = (
                            "fuel_station"
                            if state.fuel_progress == FuelProgress.EMPTY_CAN
                            else "empty_fuel_can"
                        )
                    else:
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
                capacity_increments += 1
            if removed_any:
                if capacity_increments:
                    increase_survivor_capacity(game_data, capacity_increments)
                maintain_waiting_car_supply(game_data)

    # Car hitting zombies
    if player.in_car and active_car and active_car.health > 0 and shrunk_car:
        zombies_hit = [
            zombie
            for zombie in pygame.sprite.spritecollide(
                shrunk_car, zombie_group, False
            )
        ]
        if zombies_hit:
            move_dx = getattr(active_car, "last_move_dx", 0.0)
            move_dy = getattr(active_car, "last_move_dy", 0.0)
            moving = abs(move_dx) > 0.001 or abs(move_dy) > 0.001
            moving_hits = 0
            if hasattr(active_car, "get_collision_circle"):
                car_center, car_radius = active_car.get_collision_circle()
            else:
                car_center = active_car.rect.center
                car_radius = getattr(active_car, "collision_radius", 0.0)
            marker_hits = game_data.lineformer_trains.pop_markers_colliding_circle(
                center=(float(car_center[0]), float(car_center[1])),
                radius=float(car_radius),
            )
            for zombie in zombies_hit:
                if not zombie.alive():
                    continue
                zombie_radius = getattr(zombie, "collision_radius", None)
                if zombie_radius is None:
                    zombie_radius = max(zombie.rect.width, zombie.rect.height) / 2
                zx = zombie.rect.centerx - car_center[0]
                zy = zombie.rect.centery - car_center[1]
                dist = math.hypot(zx, zy)
                if dist <= 0:
                    zx = 1.0
                    zy = 0.0
                    dist = 1.0
                overlap = car_radius + zombie_radius - dist
                allowed_overlap = min(car_radius, zombie_radius) * 0.3
                if overlap > allowed_overlap:
                    push = max(0.5, overlap - allowed_overlap)
                    zombie.x += (zx / dist) * push
                    zombie.y += (zy / dist) * push
                    zombie.rect.center = (int(zombie.x), int(zombie.y))
                if not moving:
                    continue
                if hasattr(zombie, "take_damage"):
                    zombie.take_damage(
                        CAR_ZOMBIE_HIT_DAMAGE, now_ms=state.clock.elapsed_ms
                    )
                moving_hits += 1
            if zombies_hit:
                contact_hits = len(zombies_hit) - moving_hits
                contact_hits += marker_hits
                ram_damage = CAR_ZOMBIE_RAM_DAMAGE * moving_hits
                contact_damage = CAR_ZOMBIE_CONTACT_DAMAGE * contact_hits
                total_damage = ram_damage + contact_damage
                active_car._take_damage(total_damage)
            elif marker_hits > 0:
                active_car._take_damage(CAR_ZOMBIE_CONTACT_DAMAGE * marker_hits)

    # Car hitting patrol bots
    if player.in_car and active_car and active_car.health > 0 and patrol_bot_group:
        if hasattr(active_car, "get_collision_circle"):
            (car_center_x, car_center_y), car_radius = active_car.get_collision_circle()
        else:
            car_center_x = active_car.x
            car_center_y = active_car.y
            car_radius = getattr(active_car, "collision_radius", 0.0)
        for bot in list(patrol_bot_group):
            if not bot.alive():
                continue
            dx = bot.x - car_center_x
            dy = bot.y - car_center_y
            hit_range = car_radius + getattr(bot, "collision_radius", 0.0)
            if dx * dx + dy * dy <= hit_range * hit_range:
                bot.kill()
                active_car._take_damage(CAR_WALL_DAMAGE)

    _board_survivors_if_colliding(
        game_data=game_data,
        player=player,
        active_car=active_car,
        shrunk_car=shrunk_car,
        survivor_group=survivor_group,
        survivor_boarding_enabled=survivor_boarding_enabled,
    )

    handle_survivor_zombie_collisions(game_data, config)

    _handle_car_destruction(
        game_data=game_data,
        player=player,
        car=car,
        all_sprites=all_sprites,
        survivor_boarding_enabled=survivor_boarding_enabled,
    )

    # Player getting caught by zombies
    if not player.in_car and player in all_sprites:
        shrunk_player = get_shrunk_sprite(player, 0.8)
        collisions = pygame.sprite.spritecollide(
            shrunk_player, zombie_group, False, collide_circle_custom
        )
        now = state.clock.elapsed_ms
        marker_hit = game_data.lineformer_trains.any_marker_collides_circle(
            center=(player.x, player.y),
            radius=max(1.0, float(getattr(player, "collision_radius", HUMANOID_RADIUS))),
        )
        if any(
            is_active_zombie_threat(zombie, now_ms=now) for zombie in collisions
        ) or marker_hit:
            if not state.game_over:
                player.set_zombified_visual()
                state.game_over = True
                state.game_over_at = state.clock.elapsed_ms
                schedule_timed_message(
                    state,
                    tr("game_over.scream"),
                    duration_frames=SCREAM_MESSAGE_DISPLAY_FRAMES,
                    clear_on_input=False,
                    color=BLUE,
                    now_ms=state.clock.elapsed_ms,
                )

    _handle_escape_conditions(
        game_data=game_data,
        player=player,
        car=car,
        outside_cells=outside_cells,
        survivor_boarding_enabled=survivor_boarding_enabled,
        rect_center_cell=_rect_center_cell,
    )

    return None
