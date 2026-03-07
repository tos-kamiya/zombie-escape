from __future__ import annotations

from dataclasses import dataclass
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
    ZombieKind,
)
from .constants import (
    FUEL_HINT_DURATION_MS,
    LAYER_PLAYERS,
    SURVIVOR_OVERLOAD_DAMAGE_RATIO,
)
from ..colors import BLUE, YELLOW
from ..gameplay_constants import MAX_FLASHLIGHT_EFFECT_LEVEL, MAX_SHOES_EFFECT_LEVEL
from ..localization import translate as tr
from ..models import ContactHintRecord, FuelMode, FuelProgress, GameData
from ..rng import get_rng
from ..render_constants import BUDDY_COLOR
from ..screen_constants import FPS
from ..entities import Car, TrappedZombie
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
from .utils import (
    find_nearby_offscreen_spawn_position,
    is_active_zombie_threat,
    is_entity_in_fov,
    rect_visible_on_screen,
)
from .ambient import sync_ambient_palette_with_flashlights
from .constants import SCREAM_MESSAGE_DISPLAY_FRAMES, LAYER_ZOMBIES
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
CAR_INTERACTION_RADIUS = _interaction_radius(CAR_WIDTH, CAR_HEIGHT)
FUEL_INTERACTION_RADIUS = _interaction_radius(FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT)
EMPTY_FUEL_CAN_INTERACTION_RADIUS = _interaction_radius(
    EMPTY_FUEL_CAN_WIDTH,
    EMPTY_FUEL_CAN_HEIGHT,
)
FUEL_STATION_INTERACTION_RADIUS = _interaction_radius(
    FUEL_STATION_WIDTH,
    FUEL_STATION_HEIGHT,
)
FLASHLIGHT_INTERACTION_RADIUS = _interaction_radius(
    FLASHLIGHT_WIDTH,
    FLASHLIGHT_HEIGHT,
)
SHOES_INTERACTION_RADIUS = _interaction_radius(SHOES_WIDTH, SHOES_HEIGHT)


@dataclass
class InteractionContext:
    """Per-frame interaction bundle used by interaction helpers."""

    game_data: GameData
    config: dict[str, Any]
    player: pygame.sprite.Sprite
    state: Any
    stage: Any
    original_car: Car | None
    active_car: Car | None
    waiting_cars: list[Car]
    shrunk_car: pygame.sprite.Sprite | None
    survivor_boarding_enabled: bool
    need_fuel_text: str
    need_empty_can_text: str
    flashlight_full_text: str
    shoes_full_text: str
    walkable_cells: list[tuple[int, int]]
    outside_cells: set[tuple[int, int]]
    contaminated_cells: set[tuple[int, int]]
    cell_size: int
    camera: Any
    player_mounted: bool
    player_in_active_car: bool

    def rect_center_cell(self, rect: pygame.Rect) -> tuple[int, int] | None:
        if self.cell_size <= 0:
            return None
        return (int(rect.centerx // self.cell_size), int(rect.centery // self.cell_size))

    def cell_center(self, cell: tuple[int, int]) -> tuple[int, int]:
        return (
            int((cell[0] * self.cell_size) + (self.cell_size / 2)),
            int((cell[1] * self.cell_size) + (self.cell_size / 2)),
        )

    def player_near_point(self, point: tuple[float, float], radius: float) -> bool:
        dx = point[0] - self.player.x
        dy = point[1] - self.player.y
        return dx * dx + dy * dy <= radius * radius

    def player_near_sprite(
        self,
        sprite_obj: pygame.sprite.Sprite | None,
        radius: float,
    ) -> bool:
        return bool(
            sprite_obj
            and sprite_obj.alive()
            and self.player_near_point(sprite_obj.rect.center, radius)
        )

    def player_near_car(self, car_obj: Car | None) -> bool:
        return self.player_near_sprite(car_obj, CAR_INTERACTION_RADIUS)

    def entity_on_contaminated_cell(self, entity: pygame.sprite.Sprite) -> bool:
        if self.cell_size <= 0 or not self.contaminated_cells:
            return False
        cell = (
            int(entity.rect.centerx // self.cell_size),
            int(entity.rect.centery // self.cell_size),
        )
        return cell in self.contaminated_cells


def _build_interaction_context(
    game_data: GameData,
    config: dict[str, Any],
) -> InteractionContext:
    player = game_data.player
    assert player is not None
    original_car = game_data.car
    active_car = original_car if original_car and original_car.alive() else None
    mounted_vehicle = player.mounted_vehicle
    if mounted_vehicle is not None and not mounted_vehicle.alive():
        mounted_vehicle = None
    player_mounted = mounted_vehicle is not None
    player_in_active_car = active_car is not None and mounted_vehicle is active_car
    if not player_mounted and player.in_car and active_car:
        # Legacy fallback while call sites migrate from `in_car`.
        player_mounted = True
        player_in_active_car = True
    stage = game_data.stage
    return InteractionContext(
        game_data=game_data,
        config=config,
        player=player,
        state=game_data.state,
        stage=stage,
        original_car=original_car,
        active_car=active_car,
        waiting_cars=game_data.waiting_cars,
        shrunk_car=get_shrunk_sprite(active_car, 0.8) if active_car else None,
        survivor_boarding_enabled=(
            stage.survivor_rescue_stage or stage.survivor_spawn_rate > 0.0
        ),
        need_fuel_text=tr("hud.need_fuel"),
        need_empty_can_text=tr("hud.need_empty_fuel_can"),
        flashlight_full_text=tr("hud.flashlight_full"),
        shoes_full_text=tr("hud.shoes_full"),
        walkable_cells=game_data.layout.walkable_cells,
        outside_cells=game_data.layout.outside_cells,
        contaminated_cells=game_data.layout.zombie_contaminated_cells,
        cell_size=game_data.cell_size,
        camera=game_data.camera,
        player_mounted=player_mounted,
        player_in_active_car=player_in_active_car,
    )


def _show_need_fuel_hint(ctx: InteractionContext) -> None:
    if ctx.stage.endurance_stage:
        return
    schedule_timed_message(
        ctx.state,
        ctx.need_fuel_text,
        duration_frames=_ms_to_frames(FUEL_HINT_DURATION_MS),
        clear_on_input=False,
        color=YELLOW,
        now_ms=ctx.state.clock.elapsed_ms,
    )
    if ctx.stage.fuel_mode == FuelMode.REFUEL_CHAIN:
        ctx.state.hint_target_type = (
            "fuel_station"
            if ctx.state.fuel_progress == FuelProgress.EMPTY_CAN
            else "empty_fuel_can"
        )
    else:
        ctx.state.hint_target_type = "fuel"


def _remember_contact_hint(
    game_data: GameData,
    *,
    kind: str,
    target: pygame.sprite.Sprite | None,
) -> None:
    if not (target and target.alive()):
        return
    state = game_data.state
    target_id = id(target)
    anchor_pos = (int(target.rect.centerx), int(target.rect.centery))
    for record in state.contact_hint_records:
        if record.kind == kind and record.target_id == target_id:
            record.anchor_pos = anchor_pos
            return
    state.contact_hint_records.append(
        ContactHintRecord(
            kind=kind,
            target_id=target_id,
            anchor_pos=anchor_pos,
        )
    )


def _forget_contact_hint(
    game_data: GameData,
    *,
    kind: str,
    target: pygame.sprite.Sprite | None,
) -> None:
    if target is None:
        return
    state = game_data.state
    target_id = id(target)
    state.contact_hint_records = [
        record
        for record in state.contact_hint_records
        if not (record.kind == kind and record.target_id == target_id)
    ]


def _handle_spiky_plant_trapping(game_data: GameData) -> None:
    """Check if any zombies should be trapped by spiky plants."""
    spiky_plants = game_data.spiky_plants
    if not spiky_plants:
        return
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites
    cell_size = game_data.cell_size
    if cell_size <= 0:
        return

    for zombie in list(zombie_group):
        if not zombie.alive() or getattr(zombie, "is_trapped", False):
            continue

        cell = (int(zombie.x // cell_size), int(zombie.y // cell_size))
        hp = spiky_plants.get(cell)
        if hp and hp.alive():
            dx = hp.x - zombie.x
            dy = hp.y - zombie.y
            dist_sq = dx * dx + dy * dy
            trap_range = zombie.collision_radius + hp.collision_radius
            if dist_sq <= trap_range * trap_range:
                # Replace with TrappedZombie
                trapped = TrappedZombie(
                    x=zombie.x,
                    y=zombie.y,
                    kind=getattr(zombie, "kind", ZombieKind.NORMAL),
                    health=zombie.health,
                    max_health=zombie.max_health,
                    facing_bin=getattr(zombie, "facing_bin", 0),
                    radius=zombie.radius,
                    collision_radius=zombie.collision_radius,
                    decay_duration_frames=zombie.decay_duration_frames,
                )
                zombie.kill()
                zombie_group.add(trapped)
                all_sprites.add(trapped, layer=LAYER_ZOMBIES)


def _handle_fuel_pickup(
    *,
    ctx: InteractionContext,
    fuel: pygame.sprite.Sprite | None,
) -> None:
    state = ctx.state
    if not (
        fuel
        and fuel.alive()
        and state.fuel_progress != FuelProgress.FULL_CAN
        and not ctx.player_mounted
    ):
        return
    if not ctx.player_near_point(fuel.rect.center, FUEL_INTERACTION_RADIUS):
        return
    state.fuel_progress = FuelProgress.FULL_CAN
    if state.timed_message == ctx.need_fuel_text:
        schedule_timed_message(
            state, None, duration_frames=0, now_ms=state.clock.elapsed_ms
        )
    state.hint_expires_at = 0
    state.hint_target_type = None
    fuel.kill()
    ctx.game_data.fuel = None
    print("Fuel acquired!")


def _handle_empty_fuel_can_pickup(
    *,
    ctx: InteractionContext,
    empty_fuel_can: pygame.sprite.Sprite | None,
) -> bool:
    state = ctx.state
    if not (
        empty_fuel_can
        and empty_fuel_can.alive()
        and state.fuel_progress == FuelProgress.NONE
        and not ctx.player_mounted
    ):
        return False
    if not ctx.player_near_point(
        empty_fuel_can.rect.center,
        EMPTY_FUEL_CAN_INTERACTION_RADIUS,
    ):
        return False
    state.fuel_progress = FuelProgress.EMPTY_CAN
    state.hint_expires_at = 0
    state.hint_target_type = None
    empty_fuel_can.kill()
    ctx.game_data.empty_fuel_can = None
    print("Empty fuel can acquired!")
    return True


def _handle_fuel_station_refuel(
    *,
    ctx: InteractionContext,
    fuel_station: pygame.sprite.Sprite | None,
) -> bool:
    state = ctx.state
    if not (
        fuel_station
        and fuel_station.alive()
        and state.fuel_progress == FuelProgress.EMPTY_CAN
        and not ctx.player_mounted
    ):
        return False
    if not ctx.player_near_point(
        fuel_station.rect.center,
        FUEL_STATION_INTERACTION_RADIUS,
    ):
        return False
    _remember_contact_hint(ctx.game_data, kind="fuel_station", target=fuel_station)
    state.fuel_progress = FuelProgress.FULL_CAN
    if state.timed_message == ctx.need_fuel_text:
        schedule_timed_message(
            state, None, duration_frames=0, now_ms=state.clock.elapsed_ms
        )
    schedule_timed_message(
        state,
        tr("hud.fuel_refilled"),
        duration_frames=_ms_to_frames(FUEL_HINT_DURATION_MS),
        clear_on_input=False,
        color=YELLOW,
        now_ms=state.clock.elapsed_ms,
    )
    state.hint_expires_at = 0
    state.hint_target_type = None
    print("Fuel can filled at station!")
    return True


def _handle_fuel_station_without_can_hint(
    *,
    ctx: InteractionContext,
    fuel_station: pygame.sprite.Sprite | None,
) -> None:
    state = ctx.state
    if not (
        fuel_station
        and fuel_station.alive()
        and state.fuel_progress == FuelProgress.NONE
        and not ctx.player_mounted
    ):
        return
    if not ctx.player_near_point(
        fuel_station.rect.center,
        FUEL_STATION_INTERACTION_RADIUS,
    ):
        return
    _remember_contact_hint(ctx.game_data, kind="fuel_station", target=fuel_station)
    schedule_timed_message(
        state,
        ctx.need_empty_can_text,
        duration_frames=_ms_to_frames(FUEL_HINT_DURATION_MS),
        clear_on_input=False,
        color=YELLOW,
        now_ms=state.clock.elapsed_ms,
    )
    state.hint_target_type = "empty_fuel_can"


def _handle_player_item_pickups(
    *,
    ctx: InteractionContext,
    flashlights: list[pygame.sprite.Sprite],
    shoes_list: list[pygame.sprite.Sprite],
) -> None:
    state = ctx.state
    if ctx.player_mounted:
        return
    for flashlight in list(flashlights):
        if not flashlight.alive():
            continue
        if not ctx.player_near_point(
            flashlight.rect.center,
            FLASHLIGHT_INTERACTION_RADIUS,
        ):
            continue
        if state.flashlight_count >= MAX_FLASHLIGHT_EFFECT_LEVEL:
            schedule_timed_message(
                state,
                ctx.flashlight_full_text,
                duration_frames=_ms_to_frames(400),
                clear_on_input=False,
                color=YELLOW,
                now_ms=state.clock.elapsed_ms,
            )
            break
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
        if not ctx.player_near_point(shoes.rect.center, SHOES_INTERACTION_RADIUS):
            continue
        if state.shoes_count >= MAX_SHOES_EFFECT_LEVEL:
            schedule_timed_message(
                state,
                ctx.shoes_full_text,
                duration_frames=_ms_to_frames(400),
                clear_on_input=False,
                color=YELLOW,
                now_ms=state.clock.elapsed_ms,
            )
            break
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
    ctx: InteractionContext,
    survivor_group: pygame.sprite.Group,
) -> None:
    if not (
        ctx.survivor_boarding_enabled
        and ctx.player_in_active_car
        and ctx.active_car
        and ctx.shrunk_car
        and survivor_group
    ):
        return
    state = ctx.state
    boarded_candidates = pygame.sprite.spritecollide(
        ctx.shrunk_car, survivor_group, False, collide_circle_custom
    )
    boarded = list(boarded_candidates)
    for survivor in boarded:
        survivor.kill()
    if not boarded:
        return
    state.survivors_onboard += len(boarded)
    apply_passenger_speed_penalty(ctx.game_data)
    capacity_limit = state.survivor_capacity
    if state.survivors_onboard > capacity_limit:
        overload_damage = max(
            1,
            int(ctx.active_car.max_health * SURVIVOR_OVERLOAD_DAMAGE_RATIO),
        )
        add_survivor_message(ctx.game_data, tr("survivors.too_many_aboard"))
        ctx.active_car._take_damage(overload_damage)


def _handle_car_destruction(
    *,
    ctx: InteractionContext,
) -> None:
    car = ctx.original_car
    state = ctx.state
    if not (car and car.alive() and car.health <= 0):
        return
    fell_into_pitfall = bool(getattr(car, "pending_pitfall_fall", False))
    car_destroyed_pos = car.rect.center
    eject_pos = getattr(car, "pitfall_eject_pos", None) or car_destroyed_pos
    car.kill()
    if ctx.survivor_boarding_enabled:
        drop_survivors_from_car(ctx.game_data, eject_pos)
    mounted_vehicle = getattr(ctx.player, "mounted_vehicle", None)
    player_in_destroyed_car = mounted_vehicle is car or (
        mounted_vehicle is None and ctx.player.in_car
    )
    if player_in_destroyed_car:
        ctx.player.mounted_vehicle = None
        ctx.player.x, ctx.player.y = eject_pos[0], eject_pos[1]
        ctx.player.rect.center = (int(ctx.player.x), int(ctx.player.y))
        if ctx.player not in ctx.game_data.groups.all_sprites:
            ctx.game_data.groups.all_sprites.add(ctx.player, layer=LAYER_PLAYERS)
        if fell_into_pitfall:
            print("Car fell into pitfall! Player ejected.")
        else:
            print("Car destroyed! Player ejected.")

    # Clear active car and let the player hunt for another waiting car.
    ctx.game_data.car = None
    ctx.active_car = None
    state.survivor_capacity = SURVIVOR_MAX_SAFE_PASSENGERS
    apply_passenger_speed_penalty(ctx.game_data)

    # Bring back the buddies near the player after losing the car
    respawn_buddies_near_player(ctx.game_data)
    maintain_waiting_car_supply(ctx.game_data)


def _handle_escape_conditions(
    *,
    ctx: InteractionContext,
) -> None:
    stage = ctx.stage
    state = ctx.state
    # Player escaping on foot after dawn (Stage 5)
    if (
        stage.endurance_stage
        and state.dawn_ready
        and not ctx.player_mounted
        and ctx.outside_cells
        and (player_cell := ctx.rect_center_cell(ctx.player.rect)) is not None
        and player_cell in ctx.outside_cells
    ):
        buddy_ready = True
        if stage.buddy_required_count > 0:
            buddy_ready = state.buddy_merged_count >= stage.buddy_required_count
        if buddy_ready:
            if stage.buddy_required_count > 0:
                state.buddy_rescued = min(
                    stage.buddy_required_count, state.buddy_merged_count
                )
            state.game_won = True

    # Player escaping the level
    if (
        ctx.player_in_active_car
        and ctx.original_car
        and ctx.original_car.alive()
        and state.fuel_progress == FuelProgress.FULL_CAN
    ):
        buddy_ready = True
        if stage.buddy_required_count > 0:
            buddy_ready = state.buddy_merged_count >= stage.buddy_required_count
        car_cell = ctx.rect_center_cell(ctx.original_car.rect)
        if buddy_ready and car_cell is not None and car_cell in ctx.outside_cells:
            if stage.buddy_required_count > 0:
                state.buddy_rescued = min(
                    stage.buddy_required_count, state.buddy_merged_count
                )
            if ctx.survivor_boarding_enabled and state.survivors_onboard:
                state.survivors_rescued += state.survivors_onboard
                state.survivors_onboard = 0
                apply_passenger_speed_penalty(ctx.game_data)
            state.game_won = True


def _handle_buddy_interactions(
    *,
    ctx: InteractionContext,
    zombie_group: pygame.sprite.Group,
    survivor_group: pygame.sprite.Group,
    lineformer_trains: Any,
) -> None:
    stage = ctx.stage
    state = ctx.state
    buddies = [
        survivor
        for survivor in survivor_group
        if survivor.alive() and survivor.is_buddy and not survivor.rescued
    ]
    if stage.buddy_required_count > 0 and buddies:
        for buddy in list(buddies):
            if not buddy.alive():
                continue
            buddy_on_screen = rect_visible_on_screen(ctx.camera, buddy.rect)
            if not ctx.player_mounted:
                dist_to_player_sq = (ctx.player.x - buddy.x) ** 2 + (
                    ctx.player.y - buddy.y
                ) ** 2
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
                    _remember_contact_hint(ctx.game_data, kind="buddy", target=buddy)
            elif ctx.player_in_active_car and ctx.active_car and ctx.shrunk_car:
                g = pygame.sprite.Group()
                g.add(buddy)
                if pygame.sprite.spritecollide(
                    ctx.shrunk_car, g, False, collide_circle_custom
                ):
                    prospective_passengers = state.survivors_onboard + 1
                    capacity_limit = state.survivor_capacity
                    if prospective_passengers > capacity_limit:
                        overload_damage = max(
                            1,
                            int(
                                ctx.active_car.max_health
                                * SURVIVOR_OVERLOAD_DAMAGE_RATIO
                            ),
                        )
                        add_survivor_message(
                            ctx.game_data,
                            tr("survivors.too_many_aboard"),
                        )
                        ctx.active_car._take_damage(overload_damage)
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
                radius=max(
                    1.0, float(getattr(buddy, "collision_radius", HUMANOID_RADIUS))
                ),
            )
            buddy_caught = (
                any(
                    is_active_zombie_threat(zombie, now_ms=now) for zombie in collisions
                )
                or marker_caught
            )
            if buddy.alive() and buddy_caught:
                if ctx.player_in_active_car and ctx.active_car:
                    fov_target = ctx.active_car
                else:
                    fov_target = ctx.player
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
                    if ctx.walkable_cells:
                        respawn_pos: tuple[int, int] | None = None
                        for _ in range(20):
                            candidate = find_nearby_offscreen_spawn_position(
                                ctx.walkable_cells,
                                ctx.cell_size,
                                player=ctx.player,
                                camera=ctx.camera,
                                attempts=1,
                            )
                            test_rect = buddy.rect.copy()
                            test_rect.center = candidate
                            if not is_entity_in_fov(
                                test_rect,
                                fov_target=fov_target,
                                flashlight_count=state.flashlight_count,
                            ):
                                respawn_pos = candidate
                                break
                        if respawn_pos is None:
                            new_cell = RNG.choice(ctx.walkable_cells)
                            respawn_pos = ctx.cell_center(new_cell)
                        buddy.teleport(respawn_pos)
                    else:
                        buddy.teleport(ctx.game_data.layout.field_rect.center)
                    _forget_contact_hint(ctx.game_data, kind="buddy", target=buddy)
                    buddy.following = False

    if stage.buddy_required_count > 0:
        following_count = sum(1 for buddy in buddies if buddy.following)
        state.buddy_merged_count = state.buddy_onboard + following_count
    else:
        state.buddy_merged_count = 0


def check_interactions(game_data: GameData, config: dict[str, Any]) -> None:
    """Check and handle interactions between entities."""
    ctx = _build_interaction_context(game_data, config)
    player = ctx.player
    zombie_group = game_data.groups.zombie_group
    patrol_bot_group = game_data.groups.patrol_bot_group
    carrier_bot_group = game_data.groups.carrier_bot_group
    all_sprites = game_data.groups.all_sprites
    survivor_group = game_data.groups.survivor_group
    state = ctx.state
    fuel = game_data.fuel
    empty_fuel_can = game_data.empty_fuel_can
    fuel_station = game_data.fuel_station
    flashlights = game_data.flashlights or []
    shoes_list = game_data.shoes or []
    stage = ctx.stage
    maintain_waiting_car_supply(game_data)
    _handle_spiky_plant_trapping(game_data)

    if stage.fuel_mode == FuelMode.REFUEL_CHAIN:
        picked_empty_this_frame = _handle_empty_fuel_can_pickup(
            ctx=ctx,
            empty_fuel_can=empty_fuel_can,
        )
        if not picked_empty_this_frame:
            _handle_fuel_station_refuel(
                ctx=ctx,
                fuel_station=fuel_station,
            )
            _handle_fuel_station_without_can_hint(
                ctx=ctx,
                fuel_station=fuel_station,
            )
    else:
        _handle_fuel_pickup(
            ctx=ctx,
            fuel=fuel,
        )
    _handle_player_item_pickups(
        ctx=ctx,
        flashlights=flashlights,
        shoes_list=shoes_list,
    )

    sync_ambient_palette_with_flashlights(game_data)

    _handle_buddy_interactions(
        ctx=ctx,
        zombie_group=zombie_group,
        survivor_group=survivor_group,
        lineformer_trains=game_data.lineformer_trains,
    )

    # Player entering an active car already under control
    if (
        not ctx.player_mounted
        and ctx.player_near_car(ctx.active_car)
        and ctx.active_car
        and ctx.active_car.health > 0
    ):
        _remember_contact_hint(game_data, kind="car", target=ctx.active_car)
        if state.fuel_progress >= FuelProgress.FULL_CAN:
            _forget_contact_hint(game_data, kind="car", target=ctx.active_car)
            player.mounted_vehicle = ctx.active_car
            ctx.player_mounted = True
            ctx.player_in_active_car = True
            all_sprites.remove(player)
            state.hint_expires_at = 0
            state.hint_target_type = None
            print("Player entered car!")
        else:
            _show_need_fuel_hint(ctx)

    # Claim a waiting/parked car when the player finally reaches it
    if not ctx.player_mounted and not ctx.active_car and ctx.waiting_cars:
        claimed_car: Car | None = None
        for parked_car in ctx.waiting_cars:
            if ctx.player_near_car(parked_car):
                claimed_car = parked_car
                break
        if claimed_car:
            _remember_contact_hint(game_data, kind="car", target=claimed_car)
            if state.fuel_progress >= FuelProgress.FULL_CAN:
                _forget_contact_hint(game_data, kind="car", target=claimed_car)
                try:
                    game_data.waiting_cars.remove(claimed_car)
                except ValueError:
                    pass
                game_data.car = claimed_car
                ctx.active_car = claimed_car
                player.mounted_vehicle = claimed_car
                ctx.player_mounted = True
                ctx.player_in_active_car = True
                all_sprites.remove(player)
                state.hint_expires_at = 0
                state.hint_target_type = None
                apply_passenger_speed_penalty(game_data)
                maintain_waiting_car_supply(game_data)
                print("Player claimed a waiting car!")
            else:
                _show_need_fuel_hint(ctx)

    # Bonus: collide a parked car while driving to repair/extend capabilities
    if (
        ctx.player_in_active_car
        and ctx.active_car
        and ctx.shrunk_car
        and ctx.waiting_cars
    ):
        waiting_group = pygame.sprite.Group(ctx.waiting_cars)
        collided_waiters = pygame.sprite.spritecollide(
            ctx.shrunk_car, waiting_group, False, pygame.sprite.collide_rect
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
                ctx.active_car.health = ctx.active_car.max_health
                ctx.active_car._update_color()
                removed_any = True
                capacity_increments += 1
            if removed_any:
                if capacity_increments:
                    increase_survivor_capacity(game_data, capacity_increments)
                maintain_waiting_car_supply(game_data)

    # Car hitting zombies
    if (
        ctx.player_in_active_car
        and ctx.active_car
        and ctx.active_car.health > 0
        and ctx.shrunk_car
    ):
        zombies_hit = [
            zombie for zombie in pygame.sprite.spritecollide(ctx.shrunk_car, zombie_group, False)
        ]
        if zombies_hit:
            move_dx = getattr(ctx.active_car, "last_move_dx", 0.0)
            move_dy = getattr(ctx.active_car, "last_move_dy", 0.0)
            moving = abs(move_dx) > 0.001 or abs(move_dy) > 0.001
            moving_hits = 0
            if hasattr(ctx.active_car, "get_collision_circle"):
                car_center, car_radius = ctx.active_car.get_collision_circle()
            else:
                car_center = ctx.active_car.rect.center
                car_radius = getattr(ctx.active_car, "collision_radius", 0.0)
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
                ctx.active_car._take_damage(total_damage)
            elif marker_hits > 0:
                ctx.active_car._take_damage(CAR_ZOMBIE_CONTACT_DAMAGE * marker_hits)

    # Car hitting spiky plants
    if (
        ctx.player_in_active_car
        and ctx.active_car
        and ctx.active_car.health > 0
        and ctx.shrunk_car
    ):
        car_cell_x = int(ctx.active_car.x // ctx.cell_size)
        car_cell_y = int(ctx.active_car.y // ctx.cell_size)
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                hp = game_data.spiky_plants.get((car_cell_x + dx, car_cell_y + dy))
                if hp and hp.alive():
                    if ctx.shrunk_car.rect.colliderect(hp.rect):
                        # Car destroys the plant instantly (or applies high damage)
                        # and takes minimal damage (or wall damage)
                        hp._take_damage(hp.max_health)
                        ctx.active_car._take_damage(CAR_WALL_DAMAGE // 4)

    # Car hitting patrol/carrier bots
    bot_groups = [patrol_bot_group, carrier_bot_group]
    if (
        ctx.player_in_active_car
        and ctx.active_car
        and ctx.active_car.health > 0
        and any(len(group) > 0 for group in bot_groups)
    ):
        if hasattr(ctx.active_car, "get_collision_circle"):
            (car_center_x, car_center_y), car_radius = ctx.active_car.get_collision_circle()
        else:
            car_center_x = ctx.active_car.x
            car_center_y = ctx.active_car.y
            car_radius = getattr(ctx.active_car, "collision_radius", 0.0)
        for group in bot_groups:
            for bot in list(group):
                if not bot.alive():
                    continue
                dx = bot.x - car_center_x
                dy = bot.y - car_center_y
                hit_range = car_radius + getattr(bot, "collision_radius", 0.0)
                if dx * dx + dy * dy <= hit_range * hit_range:
                    bot.kill()
                    ctx.active_car._take_damage(CAR_WALL_DAMAGE)

    _board_survivors_if_colliding(
        ctx=ctx,
        survivor_group=survivor_group,
    )

    handle_survivor_zombie_collisions(game_data, config)

    _handle_car_destruction(
        ctx=ctx,
    )

    # Player getting caught by zombies or touching a contaminated tile
    if not ctx.player_mounted and player in all_sprites:
        shrunk_player = get_shrunk_sprite(player, 0.8)
        collisions = pygame.sprite.spritecollide(
            shrunk_player, zombie_group, False, collide_circle_custom
        )
        now = state.clock.elapsed_ms
        marker_hit = game_data.lineformer_trains.any_marker_collides_circle(
            center=(player.x, player.y),
            radius=max(
                1.0, float(getattr(player, "collision_radius", HUMANOID_RADIUS))
            ),
        )
        contaminated_hit = ctx.entity_on_contaminated_cell(player)
        if (
            any(is_active_zombie_threat(zombie, now_ms=now) for zombie in collisions)
            or marker_hit
            or contaminated_hit
        ):
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
        ctx=ctx,
    )

    return None
