"""Gameplay helpers and logic utilities."""

# ruff: noqa: F401

from .ambient import set_ambient_palette, sync_ambient_palette_with_flashlights
from .footprints import get_shrunk_sprite, update_footprints
from .interactions import check_interactions
from .layout import generate_level_from_blueprint, rect_for_cell
from .movement import process_player_input, update_entities
from .spawn import (
    alive_waiting_cars,
    create_zombie,
    log_waiting_car_count,
    maintain_waiting_car_supply,
    nearest_waiting_car,
    place_buddies,
    place_flashlight,
    place_flashlights,
    place_fuel_can,
    place_new_car,
    setup_player_and_cars,
    spawn_exterior_zombie,
    spawn_initial_zombies,
    spawn_nearby_zombie,
    spawn_survivors,
    spawn_waiting_car,
    spawn_weighted_zombie,
    waiting_car_target_count,
)
from .state import carbonize_outdoor_zombies, initialize_game_state, update_survival_timer
from .survivors import (
    add_survivor_message,
    apply_passenger_speed_penalty,
    calculate_car_speed_for_passengers,
    cleanup_survivor_messages,
    drop_survivors_from_car,
    handle_survivor_zombie_collisions,
    increase_survivor_capacity,
    random_survivor_conversion_line,
    respawn_buddies_near_player,
    update_survivors,
)
from .utils import (
    find_exterior_spawn_position,
    find_interior_spawn_positions,
    find_nearby_offscreen_spawn_position,
    rect_visible_on_screen,
)

__all__ = [
    "create_zombie",
    "rect_for_cell",
    "generate_level_from_blueprint",
    "place_new_car",
    "place_fuel_can",
    "place_flashlight",
    "place_flashlights",
    "place_buddies",
    "find_interior_spawn_positions",
    "find_nearby_offscreen_spawn_position",
    "find_exterior_spawn_position",
    "spawn_survivors",
    "spawn_nearby_zombie",
    "spawn_exterior_zombie",
    "spawn_weighted_zombie",
    "update_survivors",
    "alive_waiting_cars",
    "log_waiting_car_count",
    "nearest_waiting_car",
    "calculate_car_speed_for_passengers",
    "apply_passenger_speed_penalty",
    "increase_survivor_capacity",
    "waiting_car_target_count",
    "spawn_waiting_car",
    "maintain_waiting_car_supply",
    "add_survivor_message",
    "random_survivor_conversion_line",
    "cleanup_survivor_messages",
    "drop_survivors_from_car",
    "handle_survivor_zombie_collisions",
    "respawn_buddies_near_player",
    "get_shrunk_sprite",
    "update_footprints",
    "initialize_game_state",
    "setup_player_and_cars",
    "spawn_initial_zombies",
    "update_survival_timer",
    "carbonize_outdoor_zombies",
    "process_player_input",
    "update_entities",
    "check_interactions",
    "set_ambient_palette",
    "sync_ambient_palette_with_flashlights",
]
