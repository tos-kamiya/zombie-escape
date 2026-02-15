# Level Generation

## Blueprint Legend

- `O`: outside area (victory zone)
- `B`: outer wall band
- `E`: exit
- `1`: interior wall
- `.`: walkable floor
- `P`: player spawn candidate
- `C`: car spawn candidate
- `x`: pitfall
- `h`: houseplant cell
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
3. Reserved spawn/item candidates
4. Terrain hazards/features
5. Walls / reinforcement candidates

Reserved cells are protected from incompatible terrain placement.

## Wall Algorithms

- `default`: random line segments
- `empty`: no interior walls
- `grid_wire`: merged vertical/horizontal grid-like lines with adjacency constraints
- `sparse_moore` and `sparse_moore.<int>%`: sparse scattered walls with 8-neighbor restrictions
- `sparse_ortho` and `sparse_ortho.<int>%`: sparse scattered walls with 4-neighbor restrictions

## Fuel/Item Candidate Guarantees

- `FUEL_CAN`: reserves `f` candidates.
- `REFUEL_CHAIN`: reserves both `e` and `f`, guaranteeing at least one each.
- Flashlight/shoes candidate counts are matched to stage settings.

## Fall Spawn and Overlap Policy

- `fall_spawn_zones` expands to `fall_spawn_cells`.
- `fall_spawn_floor_ratio` can add interior cells by ratio.
- Fall-spawn designation can overlap with other floor features.

## Connectivity Validation

Two BFS checks gate acceptance:

1. Car connectivity (`validate_car_connectivity`)
   - 4-direction traversal from car candidate to at least one exit.
   - Produces reachable cell set used as `car_walkable_cells`.
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
- If all attempts fail, raises `MapGenerationError` and safely returns to title flow.
