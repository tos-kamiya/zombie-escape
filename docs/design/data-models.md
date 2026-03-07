# Data Models

Primary definitions live in:
- `src/zombie_escape/models.py`
- `src/zombie_escape/world_grid.py` (shared coordinate and grid utility types/helpers)

## Refactor Tracking

- `[DONE]` Replace ad-hoc `layout_data` dictionaries returned by level generation
  with a typed runtime bundle.
  - Working name: `LayoutSpawnData`
  - Goal: reduce string-key lookups and bundle spawn/layout candidate cells into one
    explicit object shared by gameplay setup and spawn helpers.
  - Scope for this step:
    - `gameplay/layout.py` returns `LayoutSpawnData`
    - `gameplay/spawn.py` and `screens/gameplay.py` consume attributes instead of
      dictionary keys
  - Non-goal for this step:
    - no broader `GameData` redesign
    - no behavior changes in placement logic
- `[PROPOSED]` Introduce an `InteractionContext` bundle for per-frame interaction
  processing in `gameplay/entity_interactions.py`.
  - Status: design exploration only
  - Intent: gather `game_data`, active actor refs, localized strings, and precomputed
    interaction radii into one object for `check_interactions(...)`.
- `[PROPOSED]` Split gameplay screen data into immutable dependencies and mutable
  runtime state.
  - Status: design exploration only
  - Intent: separate values such as `screen`, `clock`, `config`, `stage`,
    `render_assets` from pause/input/runtime toggles inside `GameplayScreenRunner`.

## `ProgressState`

Runtime play-state bundle. Key categories:

- End state: `game_over`, `game_won`, `game_over_message`, `game_over_at`
- End-screen cache: `scaled_overview`, `overview_created`
- Effects/timers: footprints, hint timers, timed message, elapsed play ms
- Item progression: `fuel_progress`, `flashlight_count`, `shoes_count`
- Rescue progress: buddy/survivor counters and onboard counts
- Endurance stage: elapsed/goal, dawn state
- Debug/seed controls: `seed`, `debug_mode`, `time_accel_active`
- Falling spawn support: `falling_zombies`, `falling_spawn_carry`
- Ambient effects: `dust_rings`, `electrified_cells`

## `GameData`

Main aggregate passed across gameplay/render systems.

- `state`: `ProgressState`
- `groups`: sprite groups (`LayeredUpdates` + typed groups)
- `camera`: camera state
- `layout`: `LevelLayout`
- `fog`: fog caches
- `stage`: active `Stage`
- World sizing: `cell_size`, `level_width`, `level_height`
- Key entity refs: `player`, `car`, fuel/item refs, waiting cars
- Train state: `lineformer_trains`

## `LayoutSpawnData`

Typed bundle for spawn/setup candidate cells derived from the generated blueprint.

- Player/car/item candidates:
  - `player_cells`, `car_cells`, `car_spawn_cells`, `item_spawn_cells`
- Objective/item placement cells:
  - `fuel_cells`, `fuel_station_cells`, `empty_fuel_can_cells`
  - `flashlight_cells`, `shoes_cells`
- Terrain-derived candidate sets exposed to spawn/setup:
  - `walkable_cells`, `car_walkable_cells`
  - `spiky_plant_cells`, `fire_floor_cells`, `metal_floor_cells`
  - `zombie_contaminated_cells`, `puddle_cells`

Purpose:

- Replace stringly-typed layout dictionaries passed among gameplay initialization
  helpers.
- Make the spawn/setup contract explicit without inflating `GameData`.

## `Stage`

Per-stage tunables and feature toggles.

- Objective/game mode:
  - `fuel_mode` (`refuel_chain`, `fuel_can`, `start_full`)
  - buddy/survivor/endurance flags and parameters
- Spawn behavior:
  - intervals, interior/exterior/fall weights, counts per interval
- Variant ratios:
  - normal/tracker/wall-hugger/lineformer/solitary/dog ratios
  - nimble/tracker-dog ratios (`zombie_nimble_dog_ratio`, `zombie_tracker_dog_ratio`) within dog spawns
- Terrain features:
  - wall algorithm, rubble ratio, pitfall/spiky-plant/puddle settings
  - moving-floor and fall-spawn zone controls
  - reinforced inner wall controls (`reinforced_wall_density`, `reinforced_wall_zones`)
  - exit-side control via `exit_sides` (`top`, `bottom`, `left`, `right`)
- Progression controls:
  - waiting car target count, intro line key, availability
- Grid scale:
  - cell size and grid dimensions

## `LevelLayout`

Generated map surface and cell sets.

- `field_rect`
- `outside_cells`, `walkable_cells`, `wall_cells`, `outer_wall_cells`, `steel_beam_cells`
- `car_walkable_cells`, `car_spawn_cells`
- `pitfall_cells`, `fall_spawn_cells`
- `spiky_plant_cells`, `puddle_cells`
- `floor_ruin_cells` (precomputed floor-decoration placement map: `(x, y) -> variant`)
- `bevel_corners`

Naming convention: `*_cells` stores cell-coordinate collections.

## `Groups`

Contains `all_sprites` (`LayeredUpdates`) and typed subsets (`wall_group`, `zombie_group`, `survivor_group`, `patrol_bot_group`).
