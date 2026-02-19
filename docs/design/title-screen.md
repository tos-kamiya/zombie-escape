# Title Screen

## Stage Select Icons

The stage-select mini-icons are built in `src/zombie_escape/screens/title.py` via `_get_stage_icons(stage)`.

Icons are shown only for stages that are both:
- Cleared at least once.
- Currently available/unlocked.

Icon order is fixed by category:

1. Clear-condition related
- `car_forbidden` only for endurance (carless) stages.
- `fuel_can` for `FuelMode.FUEL_CAN`.
- `empty_fuel_can` for `FuelMode.REFUEL_CHAIN` (fuel station is intentionally not shown).
- `buddy` when `buddy_required_count > 0`.
- `survivor` when `survivor_rescue_stage` is enabled.

2. Zombies and plants
- `zombie` (normal) when that ratio is present.
- `zombie_tracker` when that ratio is present.
- `zombie_wall` when that ratio is present.
- `zombie_line` when that ratio is present.
- `zombie_dog` when that ratio is present.
- `spiky_plant` when spiky-plant hazard settings are present.

3. Environment (floor)
- `fall_spawn` when falling spawn floor settings are present.
- `pitfall` when pitfall settings are present.
- `moving_floor` when moving floor settings are present.
- `puddle` when puddle settings are present.

4. Helper signals
- `flashlight_forbidden` only when `initial_flashlight_count <= 0`.
- `shoes` when `initial_shoes_count > 0`.
- `patrol_bot` when `patrol_bot_spawn_rate > 0`.

## Intentional Exceptions

- Regular `car` icon is not shown, because it appears in almost all stages and adds little information value.
- Regular `flashlight` icon is not shown; only the "not available" exception is shown as `flashlight_forbidden`.
- In stage-select icons, the car sprite is rotated 90 degrees right to improve readability in the compact icon row.
- `car_forbidden` and `flashlight_forbidden` share one fixed drawing style:
  - same canvas size (flashlight icon size),
  - same X geometry/position,
  - same line thickness.

## Stage List Paging

- Stage pages can be switched by keyboard/gamepad left-right input.
- Page unlock rule:
  - Page 1 (Stages 1-5) is always available.
  - To unlock the next page, clear at least 5 stages on the current page.
  - If fewer than 5 stages are cleared on the current page, the next page remains locked.
  - This means:
    - Clear all Stages 1-5 to unlock the Stages 6-15 page.
    - Clear 5 or more stages on the Stages 6-15 page to unlock the Stages 16-25 page.
    - The same rule repeats for later pages.
- Exception: when the selected resource row is `Display Mode/Window Size`,
  left-right input changes window scale instead of switching stage pages.
- The `STAGES` header also shows mouse-clickable left/right triangle buttons when paging in that direction is possible.
- Mouse wheel input over the stage-list pane also switches stage pages:
  - wheel up: previous page
  - wheel down: next page

## Resource Menu Rows

- Resource rows are shown on every title page (stages 1-5 and later stage-group pages).
- Row order is fixed as:
  1. `Display Mode/Window Size`
  2. `Settings`
  3. `README/LICENSE` (or stage-group guide row on later pages)
  4. `Quit`
