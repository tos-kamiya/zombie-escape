 Stage 5 Design Summary

- Stage metadata
    - Extend Stage with survival-specific knobs: survival_stage (bool),
      survival_goal_ms (real countdown), interior/exterior spawn weights,
      fuel_spawn_count.
    - Stage 5 entry: requires_fuel=True, survival_stage=True, survival_goal_ms
      = 1_200_000 (20 min), spawn weights tuned so interior share rises while
      total spawn rate matches other stages, fuel_spawn_count = 0.
- State & initialization
    - ProgressState adds survival_elapsed_ms, survival_goal_ms, dawn_ready,
      dawn_prompt_at, time_accel_active, offscreen_spawn_timer,
      dawn_carbonized.
    - initialize_game_state seeds those from the stage info, forces
      has_fuel=False, and keeps fuel placement count at zero for Stage 5.
- Fuel & cars
    - place_fuel_can respects stage.fuel_spawn_count; Stage 5 gives zero, so
      no cans appear.
    - Because fuel is never acquired, existing car-entry code already blocks
      driving without extra flags.
- Time acceleration
    - Gameplay loop checks the acceleration key (e.g., Shift) and uses
      substeps (step_count = accel ? 4 : 1) with clamped sub_dt (≤ 1/30 s).
    - Each substep increments state.elapsed_play_ms; state.time_accel_active
      drives the HUD icon.
- Survival countdown & win flow
    - update_survival_timer(game_data, dt_ms) updates survival_elapsed_ms,
      flips dawn_ready when it reaches survival_goal_ms, and timestamps
      dawn_prompt_at.
    - Win condition: once dawn_ready, walking through an existing exit on foot
      wins; car escape stays locked due to missing fuel.
- Off-screen zombie pressure
    - spawn_nearby_zombie(game_data) spawns just beyond the camera but near
      the player, respecting a minimum buffer.
    - Survival stages bias the weighted spawner toward the near-player helper
      so interior pressure increases without raising the total spawn rate.
- Dawn aftermath
    - On the first dawn_ready, carbonize outdoor zombies (swap for passive
      sprites) and set state.dawn_carbonized so it runs once.
- HUD & messaging
    - Objective text: “Survive until dawn” before dawn_ready, “Get outside”
      afterward.
    - Timer bar at the bottom: compute display_remaining_ms = remaining_ms *
      (4 hours / 20 minutes) on the fly (no stored display_duration_ms),
      render HH:MM plus progress bar, show >> 4x when time_accel_active.
    - Show “Dawn has come. Get outside.” until the player exits once
      dawn_ready is true.
- Localization & docs
    - Add strings for Stage 5 title/description, survival objectives, timer
      labels, acceleration hint, dawn message; mention Stage 5 and the
      acceleration key in README.

Palette transitions remain deferred.
