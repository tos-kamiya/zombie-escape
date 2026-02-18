# Gameplay Flow

## Fire Floor Runtime Rules

- Fire floor (`fire_floor_cells`) behavior:
  - Player/Buddy: stepping on fire floor triggers immediate game over.
  - Survivor: stepping on fire floor immediately burns out (removed).
  - Zombies (all variants, including dogs): stepping on fire floor immediately burns out (removed).
  - Patrol bots and cars are unaffected and can move over fire floor normally.
- Visual FX intent:
  - Burn-out uses a short death/fall-like effect path for consistency with existing
    transient disappearance effects.
  - Runtime load control: decay masks are prebuilt at startup in three variants for
    each tone (`grayscale` / `burned`), then one variant is chosen per effect via
    Python's `random` module (separate from deterministic gameplay RNG).
- Spawn/item rule:
  - Runtime item placement candidates are derived from `item_spawn_cells`, which
    will already exclude fire floor cells.

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
- `src/zombie_escape/screens/gameplay.py` (runtime event handling, pause transitions, mouse-accel arming, and debug-only pause marker)

## Pause and Window Events

- Gameplay enters manual pause on:
  - `P`/Start or `ESC`/Select in normal play flow.
  - Corner hotspot left-click.
  - Window mode changes via `[` / `]` / `F`.
  - Runtime resize events (`VIDEORESIZE`, `WINDOWSIZECHANGED`).
- In `--debug` runs (pause overlay hidden), paused state renders a small `-- paused --` marker near the top edge.
- In `--debug` runs, releasing left mouse button while paused resumes gameplay (equivalent to selecting `Resume` in normal pause UI).
- Pause menu includes a `Toggle Fullscreen` item in addition to `Resume` and `Return to Title`.

## Spawn Phase

Major spawn functions in `gameplay/spawn.py`:

- Exterior and weighted spawns
- Spawn-position search helpers
- Falling zombie handling (`spawn` and `pitfall` modes)
- Survivor and buddy placement
- Fuel-chain/FUEL_CAN item placement
- Flashlight/shoes placement
- Waiting car maintenance and replenishment

Initial placement policy:

- Initial interior spawn-rate placements (zombies/survivors/patrol bots) use
  candidate collection + shuffle + fixed-count selection.
- Target count uses `round(candidate_count * spawn_rate)`.
- If `spawn_rate > 0` and the rounded result is `0`, one spawn is guaranteed
  (when candidates exist).
- Patrol bots use zero spawn jitter for initial placement, so they stay on
  human-walkable cell centers.
- Initial zombie kind composition uses stage ratios to build a fixed-count plan
  for that initial batch, then shuffles the plan before assignment.

## Update Phase

- `process_player_input(...)`
  - Produces movement vectors for player/car control contexts.
- `update_entities(...)`
  - Applies movement, camera updates, AI updates, pitfall/jump handling.
  - Includes tile-edge steering correction near walls.
- Mouse acceleration (`4x`) requires left-button press-down on the player before hold is considered valid.
- Hovering the cursor over the player (without pressing left button) displays static `>> 4x` near the player.
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

## Contact-Memory Guide Arrows

- Goal:
  - Optional player-support feature that remembers contacted objective points and
    shows subtle directional arrows to those remembered locations.
- Settings:
  - New dedicated setting (not merged into existing `car_hint`).
  - Default is `OFF`.
- Tracked targets:
  - Car and buddy are always eligible.
  - Fuel station is also eligible on stages where it appears.
  - Fuel station arrow is hidden while the player is carrying a full fuel can.
- Registration timing:
  - Register at interaction success events (not raw collision overlap).
  - Records keep target identity and anchor position.
- Runtime target resolution:
  - Buddy uses live position each frame while the record is valid.
  - Car/fuel-station use remembered anchor positions.
- Multiple records:
  - If multiple targets are registered, render one marker per record.
- Visibility and priority:
  - Contact markers are visible in both gameplay and paused gameplay views.
  - Marker style:
    - Buddy: hollow white circle marker.
    - Car/Fuel station: hollow subtle triangle marker.
  - If existing timed hint (`car_hint`) is currently visible, contact-memory arrows
    are hidden for that frame.
- Invalidation:
  - Remove record when the corresponding target is removed/replaced (despawn, death,
    respawn replacement).
  - Buddy records are also removed when buddy is force-relocated.
- Reset scope:
  - Reset all records on game over.
  - Retry starts fresh (no carry-over).

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
