# Level Generation

## Fire Floor and Metal Floor

- New terrain cells:
  - `fire_floor_cells`: lethal floor for humanoids and zombies.
  - `metal_floor_cells`: visual-only floor variant generated around fire floors.
- Stage parameters:
  - `fire_floor_density`
  - `fire_floor_zones`
  - `metal_floor_density`
  - `metal_floor_zones`
- Blueprint placement:
  - Fire floor supports both zone placement and density placement.
  - Metal floor supports both zone placement and density placement.
  - Fire floor cells are reserved against spawn/item candidate placement.
  - Stage-defined metal floor cells are placed before other hazards and are kept
    from being replaced by pitfall/puddle/spiky-plant/reinforced-wall placement.
  - Runtime spawn candidates (`item_spawn_cells`, `car_spawn_cells`, filtered `car_cells`)
    exclude fire floors, moving floors, and spiky-plant cells.
- Adjacency decoration:
  - Orthogonally adjacent normal floor cells next to fire floors are converted to
    `metal_floor_cells` for visual transition.
  - `metal_floor_cells` keep normal floor behavior (walkable, spawn-eligible,
    no hazard effect).
- Connectivity validation:
  - Fire floor is treated as blocked for humanoid objective-path validation.
  - Car connectivity keeps existing passability rules.

## Blueprint Legend

- `O`: outside area (victory zone)
- `B`: outer wall band
- `R`: reinforced inner wall (non-destructible)
- `E`: exit
- `1`: interior wall
- `.`: walkable floor
- `P`: player spawn candidate
- `C`: car spawn candidate
- `x`: pitfall
- `h`: spiky plant cell
- `w`: puddle cell
- `e`: empty fuel can candidate
- `f`: fuel-related candidate (fuel can or fuel station by mode)
- `l`: flashlight candidate
- `s`: shoes candidate
- `^`,`v`,`<`,`>`: moving floor directions

## Generation Order

`generate_random_blueprint(...)` builds map features roughly in this order:

1. Outside ring
2. Exit
3. Corner outer-wall patch for closed exit sides
4. Reserved spawn/item candidates
5. Terrain hazards/features
6. Walls / reinforcement candidates

Reserved cells are protected from incompatible terrain placement.

## Ratio-Based Cell Selection

- Density-based terrain placement (`pitfall`, `puddle`, `spiky plant`, `reinforced wall`)
  uses candidate collection + shuffle + fixed-count selection.
- Target count is calculated as `round(candidate_count * density)`.
- If `density > 0` and the rounded result is `0`, one cell is still selected.
- If `density > 0` but candidate count is `0`, blueprint generation raises
  `MapGenerationError` (treated as retryable generation failure).

## Exit Side Rule

- `Stage.exit_sides` selects which sides (`top`, `bottom`, `left`, `right`) can have exits.
- Exit placement prefers positions one cell away from each side's ends
  (near-corner positions are avoided when map size allows).
  - If the map is too small for that margin, placement falls back to the full side range.
- If a side is not included in `exit_sides`, the two corners on that side are forced to `B`
  (outer wall) even though edge cells are normally `O`.
- Example: when `exit_sides=["top","bottom"]`, both left-side and right-side corners
  are `B`: `(0,0)`, `(0,max_y)`, `(max_x,0)`, `(max_x,max_y)`.

## Wall Algorithms

- `default`: random line segments
- `empty`: no interior walls
- `grid_wire`: merged vertical/horizontal grid-like lines with adjacency constraints
- `sparse_moore` and `sparse_moore.<int>%`: sparse scattered walls with 8-neighbor restrictions
- `sparse_ortho` and `sparse_ortho.<int>%`: sparse scattered walls with 4-neighbor restrictions

## Reinforced Inner Walls

- Stage parameters:
  - `reinforced_wall_density`: density-based placement ratio
  - `reinforced_wall_zones`: explicit zone-based placement
- Behavior:
  - Treated as an interior wall for layout/collision (`wall_cells`).
  - Non-destructible using the same high-health policy as outer walls.
  - Not affected by rubble conversion (`wall_rubble_ratio` does not apply).
- Overlap policy:
  - Must not overlap with moving floors.
  - Other overlap policies are to be finalized separately.
- Visual direction:
  - Base tone close to outer walls, but with a clearly distinguishable appearance.
  - Final art details are deferred.

## Steel Beam Cell Tracking

- Steel beams are tracked as `LevelLayout.steel_beam_cells` (separate from `wall_cells`).
- If a steel beam is spawned from a destructible interior wall, the wall cell is removed
  from `wall_cells` and the beam cell is tracked in `steel_beam_cells`.
- When a steel beam is destroyed, its cell is removed from `steel_beam_cells`.

## Fuel/Item Candidate Guarantees

- `FUEL_CAN`: reserves `f` candidates.
- `REFUEL_CHAIN`: reserves both `e` and `f`, guaranteeing at least one each.
- Flashlight/shoes candidate counts are matched to stage settings.

## Fall Spawn and Overlap Policy

- `fall_spawn_zones` expands to `fall_spawn_cells`.
- `fall_spawn_cell_ratio` adds interior cells by fixed-count sampling:
  - candidate list from interior walkable cells
  - shuffle + `round(len(candidates) * ratio)` selection
  - if `ratio > 0`, minimum selection count is `1` (when candidates exist)
- `fall_spawn_cells` is a spawn-tag attribute (not a terrain tile type).
- Fall-spawn designation can overlap with other floor features.

## Connectivity Validation

Two BFS checks gate acceptance:

1. Car connectivity (`validate_car_connectivity`)
   - 4-direction traversal from car candidate to at least one exit.
   - Produces reachable cell set used as `car_walkable_cells` (pathing domain).
   - Runtime placement uses filtered `car_spawn_cells` (spawn-safe subset).
   - Skipped for endurance stages (on-foot objective validation is used instead).
2. Humanoid objective connectivity (`validate_humanoid_objective_connectivity`)
   - 8-direction traversal with moving-floor directional constraints.
   - Treats pitfall (`x`) and outer wall band (`B`) as blocked for path checks.
   - Objective conditions by fuel mode:
   - `FUEL_CAN`: `P -> reachable f -> C`
   - `REFUEL_CHAIN`: `P -> reachable e -> reachable f -> C` (strict order)
   - Endurance stages additionally require `P -> reachable E` (on-foot escape path).
   - `START_FULL`: `P -> C`

`validate_connectivity` requires both checks to pass.

## Retry Logic

- On failure, generation retries with `seed + attempt_index`.
- Maximum retries: 20.
- Retry covers both connectivity failures and blueprint-generation failures
  (including ratio-positive / zero-candidate density placement).
- If all attempts fail, raises `MapGenerationError` and safely returns to title flow.

## Blueprint Generation Structure (Current)

`generate_random_blueprint(...)` is organized as composable helpers with unchanged
runtime behavior and generation order:

1. Base grid and exits
   - `_init_grid`
   - `_place_exits`
   - `_place_corner_outer_walls_for_closed_sides`
2. Reserved/moving-floor preparation
   - `_prepare_reserved_cells`
   - `_stamp_moving_floor_cells`
3. Zone placement block
   - `_place_zone_features`
4. Objective/item token placement block
   - `_place_objective_tokens`
5. Wall algorithm resolution + density placement + wall painting
   - `_resolve_wall_algorithm_settings`
   - `_place_density_features`
   - `_place_walls_with_algorithm`
6. Post-process and finalize
   - `_place_metal_adjacent_to_fire_floor`
   - `_place_steel_beams`
   - `Blueprint(grid=..., steel_cells=...)`

## Connectivity Utility Structure (Current)

- Humanoid passable-cell collection is centralized in `_collect_humanoid_passable_cells`.
- Token-cell collection (`P`, `C`, `e`, `f`, `E`) is centralized in `_collect_token_cells`.
- Objective path validation still uses `validate_humanoid_objective_connectivity`.
- Car path validation still uses `validate_car_connectivity`.
- Combined acceptance gate remains `validate_connectivity`.

## Layout Builder Structure (Current)

`generate_level_from_blueprint(...)` uses dedicated helpers for setup-only concerns:

- `_compute_objective_item_counts`: per-stage objective-item counts
- `_resolve_steel_chance`: steel toggle/chance parsing from config
- `_build_level_layout_container`: `LevelLayout` initialization

Public data contract remains unchanged:

- `LevelLayout` fields used by runtime systems are preserved.
- `layout_data` keys (`player_cells`, `car_cells`, `fuel_cells`, `item_spawn_cells`,
  `car_spawn_cells`, etc.) are preserved.
