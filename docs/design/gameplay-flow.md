# Gameplay Flow

## Pitfalls and Jumping

- Player/car treat pitfall as blocked terrain by default.
- Car can still fall if center is pulled close enough to pit center.
- Humanoids can auto-jump over pitfall if a safe landing tile exists ahead.
- Jumping uses temporary scale and shadow offset visuals.
- Zombies do not jump and can fall immediately.

## Initialization

- `initialize_game_state(config, stage)` creates core state containers.
- `generate_level_from_blueprint(game_data, config)` builds map structures and connectivity metadata.
- `setup_player_and_cars(...)` places player and initial cars on valid reachable tiles.
- `spawn_initial_zombies(...)` seeds initial zombie populations.

Key implementation files:
- `src/zombie_escape/stage_constants.py` (stage feature flags and progression defaults consumed by init/spawn)
- `src/zombie_escape/gameplay/entity_updates.py` (frame-level movement/AI/timer update orchestration)
- `src/zombie_escape/input_utils.py` (screen-agnostic action mapping and input snapshots)
- `src/zombie_escape/screens/gameplay.py` (runtime event handling, pause transitions, and debug-only pause marker)

## Pause and Window Events

- Gameplay enters manual pause on:
  - `P`/Start or `ESC`/Select in normal play flow.
  - Corner hotspot mouse hover.
  - Window mode changes via `[` / `]` / `F`.
  - Runtime resize events (`VIDEORESIZE`, `WINDOWSIZECHANGED`).
- In `--debug` runs (pause overlay hidden), paused state renders a small `-- paused --` marker near the top edge.

## Spawn Phase

Major spawn functions in `gameplay/spawn.py`:

- Exterior and weighted spawns
- Spawn-position search helpers
- Falling zombie handling (`spawn` and `pitfall` modes)
- Survivor and buddy placement
- Fuel-chain/FUEL_CAN item placement
- Flashlight/shoes placement
- Waiting car maintenance and replenishment

## Update Phase

- `process_player_input(...)`
  - Produces movement vectors for player/car control contexts.
- `update_entities(...)`
  - Applies movement, camera updates, AI updates, pitfall/jump handling.
  - Includes tile-edge steering correction near walls.
- `check_interactions(...)`
  - Handles pickups, rescue boarding, car destruction, and win/loss logic.
  - Handles houseplant trap overflow conversion into zombie-contaminated tiles.
- `update_survivors(...)`
  - Survivor/buddy following and obstacle-aware movement.
- `handle_survivor_zombie_collisions(...)`
  - Survivor-zombie contact outcomes and contamination-tile infection conversion.
- `update_footprints(...)`
  - Footprint recording and expiration.

## Fuel Mode Flows

- `REFUEL_CHAIN`:
  - Empty can pickup -> fuel station refuel -> full fuel state.
  - Station contact without empty can shows hint and sets target.
- `FUEL_CAN`:
  - Direct pickup to full fuel state.
- Any fuel-state transition clears existing fuel hints.

## Endurance and Ambient

- `update_endurance_timer(...)` manages endurance progress and dawn transition.
- `carbonize_outdoor_zombies(...)` handles dawn event effects.
- `sync_ambient_palette_with_flashlights(...)` keeps palette in sync with flashlight state.

## Buddy Stage Win Condition

Win requires both:

- Escape condition:
  - With cars: reach outside while driving.
  - Carless endurance stage: reach target survival time.
- Buddy condition:
  - `buddy_onboard + nearby_following_buddies >= buddy_required_count`.
