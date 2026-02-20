# Architecture

## Module Overview

- `src/zombie_escape/zombie_escape.py`
  - Entry point. Parses CLI options, initializes pygame-ce, and runs the screen loop.
- `src/zombie_escape/input_utils.py`
  - Shared keyboard/gamepad input abstraction used by title/settings/gameplay screens.
- `src/zombie_escape/windowing.py`
  - Window mode control, logical-size scaling, fullscreen toggles, and presentation bridge.
- `src/zombie_escape/screens/`
  - Title/settings/gameplay/game-over screen implementations and transitions.
  - Stage-select UI includes mini-icons for stage traits.
- `src/zombie_escape/gameplay/`
  - Core game logic split by responsibility:
  - `state.py`: game-state initialization and endurance timers.
  - `layout.py`: map generation integration.
  - `spawn.py`: entity and item placement/spawn maintenance.
  - `movement.py`: player/car movement and world updates.
  - `entity_interactions.py`: pickups, rescue logic, win/lose checks.
  - `survivors.py`: survivor/buddy movement and collision handling.
  - `lineformer_trains.py`: lineformer train lifecycle and marker behavior.
- `src/zombie_escape/entities/`
  - Sprite entities (player, zombie, survivor, car, walls, bots, items).
- `src/zombie_escape/render/`
  - Rendering pipeline modules:
  - `core.py`: world + entities + fog + HUD orchestration.
  - `world_tiles.py`: playfield and footprint rendering.
  - `entity_layer.py`: sprite and lineformer marker rendering.
  - `fog.py`: fog cache and fog compositing.
  - `fx.py`: falling/decay/fade visual effects compositing.
  - `decay_effects.py`: decay effect generation/state update (grayscale and burned variants).
  - `text_overlay.py`: wrapped text and pause overlay rendering.
  - `hud.py`: objective and status overlays.
  - `shadows.py`: shadow generation.
- `src/zombie_escape/overview.py`
  - Game-over/debug overviews.
- `src/zombie_escape/level_blueprints.py`
  - Random blueprint generation and constraints.
- `src/zombie_escape/stage_constants.py`
  - Canonical stage catalog (`STAGES`) and per-stage feature configuration.
- `src/zombie_escape/models.py`
  - Core dataclasses and enums shared across gameplay/render/screen layers.
- `src/zombie_escape/world_grid.py`
  - Grid and coordinate helpers used by generation, movement, and rendering code.
- `src/zombie_escape/config.py`
  - Config defaulting and persistence.
- `src/zombie_escape/progress.py`
  - Stage clear-count persistence.
- `src/zombie_escape/rng.py`
  - Deterministic MT19937 implementation.
- `src/zombie_escape/localization.py`, `src/zombie_escape/locales/`
  - UI localization and locale resources.
- `src/zombie_escape/render_assets.py`
  - Procedural sprite/icon surface builders shared by HUD, title icons, and exports.

## Screen Transitions

- `ScreenID` has six states: `STARTUP_CHECK`, `TITLE`, `SETTINGS`, `GAMEPLAY`, `GAME_OVER`, `EXIT`.
- `main()` handles transitions via `ScreenTransition`.
- Boot guard (`STARTUP_CHECK`) waits for release of held confirm input plus a short delay.
- Boot guard also validates bundled/runtime fog cache availability for all used
  cell sizes before allowing transition to `TITLE`.
- Main gameplay runs in `screens/gameplay.py:gameplay_screen()`.

## Rendering/Collision Policy Notes

- Keep `radius` (visual size) separate from `collision_radius` (gameplay hit checks).
- Fallback to `radius` if `collision_radius` is not defined on a sprite.
