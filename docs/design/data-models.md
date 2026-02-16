# Data Models

Primary definitions live in:
- `src/zombie_escape/models.py`
- `src/zombie_escape/world_grid.py` (shared coordinate and grid utility types/helpers)

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

## `Stage`

Per-stage tunables and feature toggles.

- Objective/game mode:
  - `fuel_mode` (`refuel_chain`, `fuel_can`, `start_full`)
  - buddy/survivor/endurance flags and parameters
- Spawn behavior:
  - intervals, interior/exterior/fall weights, counts per interval
- Variant ratios:
  - normal/tracker/wall-hugger/lineformer/dog ratios
  - nimble-dog ratio (`zombie_nimble_dog_ratio`) within dog spawns
- Terrain features:
  - wall algorithm, rubble ratio, pitfall/houseplant/puddle settings
  - moving-floor and fall-spawn zone controls
  - reinforced inner wall controls (`reinforced_wall_density`, `reinforced_wall_zones`)
- Progression controls:
  - waiting car target count, intro line key, availability
- Grid scale:
  - cell size and grid dimensions

## `LevelLayout`

Generated map surface and cell sets.

- `field_rect`
- `outside_cells`, `walkable_cells`, `wall_cells`, `outer_wall_cells`
- `pitfall_cells`, `fall_spawn_cells`
- `houseplant_cells`, `puddle_cells`
- `bevel_corners`

Naming convention: `*_cells` stores cell-coordinate collections.

## `Groups`

Contains `all_sprites` (`LayeredUpdates`) and typed subsets (`wall_group`, `zombie_group`, `survivor_group`, `patrol_bot_group`).
