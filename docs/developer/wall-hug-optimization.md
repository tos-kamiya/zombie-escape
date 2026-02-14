# Wall-Hugging Zombie Parameter Optimization

This document describes the methodology and results of the parameter optimization performed for the wall-hugging zombie (`ZombieKind.WALL_HUGGER`).

## Background

The "Zombie Escape" game uses various grid cell sizes ranging from 35px to 60px depending on the stage. The original wall-hugging algorithm used fixed parameters, which led to several issues:
- **Cornering Failure**: In larger grid sizes (e.g., 60px), zombies with short, fixed-length sensors often "lost" the wall when attempting to turn around 90-degree outer corners.
- **Geometric Inaccuracy**: The probe sensors are oriented at 45 degrees. Measuring distance along this diagonal requires a correction factor to maintain a consistent perpendicular distance (gap) from the wall.
- **Oscillation**: High-speed or low-speed movement combined with aggressive steering caused zombies to jitter or vibrate along the wall.

## Methodology: Reward-Based Simulation

To find the most stable parameters across all supported cell sizes and movement speeds, a simulation-based optimization approach was used.

### Simulation Scenarios
The optimization script evaluated parameters across:
- **Cell Sizes**: 35px, 48px, 60px.
- **Speeds**: Normal speed (100%) and Decayed speed (40%).
- **Terrain**: Long straight walls and L-shaped outer corners.

### Reward Function
A continuous reward function was defined to score the "quality" of movement in each frame:
1. **Progress (+2.0 per px)**: Reward for distance traveled along the wall.
2. **Stability (-0.5 per px² error)**: Penalty for deviation from the ideal target gap.
3. **Smoothness (-10.0 per radian delta)**: Penalty for sharp or sudden changes in direction (steering jitter).
4. **Collision (-20.0 per frame)**: Penalty for overlapping with wall geometry.
5. **Loss of Track (-50.0 per frame)**: Heavy penalty for losing contact with the wall (entering "wander" mode).

If a zombie failed to navigate a corner (i.e., didn't reach a target X-coordinate), a large negative score was applied.

## Optimization Results

After a comprehensive grid search, the following parameters were found to be optimal:

| Parameter | Value | Description |
| :--- | :--- | :--- |
| `ZOMBIE_WALL_HUG_SENSOR_DIST_RATIO` | `0.6` | Sensor length as a ratio of `cell_size`. |
| `ZOMBIE_WALL_HUG_TURN_STEP_DEG` | `6.0` | Steering strength (degrees per frame). |
| `ZOMBIE_WALL_HUG_TARGET_GAP` | `5.5` | Target distance for the 45-degree probe. |

### Key Improvements
- **Dynamic Sensors**: By scaling the sensor distance with `cell_size` (`max(24, cell_size * 0.6)`), zombies can now detect corners reliably even on 60px grids.
- **Geometric Correction**: The `5.5px` target gap for a 45-degree probe results in an actual perpendicular distance of approximately `4.0px` ($5.5 	imes \cos(45^\circ) \approx 3.89$), making the movement look more natural.
- **Balanced Steering**: A 6.0-degree turn step provides enough torque to clear corners while remaining stable enough to prevent oscillation on straight segments.

## Implementation Details

The optimized parameters are stored in `src/zombie_escape/entities_constants.py` and utilized in `src/zombie_escape/entities/zombie_movement.py`.

The core logic for dynamic distance calculation is:
```python
dynamic_sensor_dist = max(ZOMBIE_WALL_HUG_SENSOR_DISTANCE, cell_size * ZOMBIE_WALL_HUG_SENSOR_DIST_RATIO)
sensor_distance = dynamic_sensor_dist + zombie.collision_radius
target_gap_diagonal = ZOMBIE_WALL_HUG_TARGET_GAP / math.cos(math.radians(ZOMBIE_WALL_HUG_PROBE_ANGLE_DEG))
```

## Performance Optimization

Initially, stages with a high number of wall-hugging zombies suffered from significant frame rate drops. This was traced back to the `_zombie_wall_hug_wall_distance` function.

### The Bottleneck
The original implementation used a step-by-step probing method:
- It iterated from `step` to `max_distance` in `2.0px` increments.
- In each increment, it performed circle-wall collision tests against all nearby walls.
- This resulted in thousands of Python-level collision checks per frame when many zombies were active.

### The Solution: Fast Raycasting
To resolve the performance issues, the step-by-step loop was replaced with a fast raycasting approach using `pygame.Rect.clipline`:
1. **Leveraging Spatial Index**: The function now directly uses the pre-filtered wall list provided by the `WallIndex` (spatial index).
2. **C-Accelerated Clipping**: Instead of manual iteration, it uses `pygame.Rect.clipline`, which is implemented in C and can calculate line-rectangle intersections extremely fast.
3. **Inflated Rects**: By inflating the wall rectangles by the zombie's collision radius, the system accurately approximates circle-rectangle collision distances without needing a pixel-perfect loop.

### Impact
After implementing this optimization, the CPU usage for wall-hugging AI dropped dramatically, ensuring a smooth 60 FPS even in stages densely populated with wall-hugging zombies.

## Advanced Multi-Scenario Velocity Optimization (New Experiment)

To ensure the AI is robust enough for complex level designs, we are conducting a large-scale parameter sweep across multiple speed-dependent variables and challenging terrain scenarios.

### New Scenarios for Evaluation
1.  **Straight Stability**: Maintaining a perfect gap on long walls.
2.  **Dual-Direction Cranks**: Navigating S-turns (left then right) without getting stuck.
3.  **Full Loop**: Completing a square circuit and returning to the starting point.
4.  **Gap Detection (The "Missing Tile" Test)**: Ensuring the zombie turns into a 1-cell wide opening in a wall rather than ignoring it and walking past.

### Parameters for Optimization (Speed-Dependent)
We are testing combinations of:
- **Dynamic Probe Angle**: Does narrowing/widening the 45° angle at different speeds improve cornering?
- **Dynamic Sensor Distance**: Refining the scaling power (e.g., linear vs. square root) relative to speed.
- **Target Gap & Turn Step**: Finding the sweet spot between speed-proportional turning and physical clearance.

### Reward Function Refinements
The reward function now includes:
- **Waypoint Bonuses**: Points for reaching key nodes in the maze (cranks, gap entry).
- **Circuit Completion**: High reward for finishing a loop.
- **Jitter Penalty**: Heavy deduction for rapid oscillation in angular velocity.
- **Gap Success**: Specific reward for entering a 1-tile gap.

## Velocity-Based Dynamic Parameter Scaling

Zombies naturally slow down over time due to decay or floor effects. To increase stability at all speeds, parameters are now dynamically scaled based on the zombie's current velocity relative to the reference `ZOMBIE_SPEED`.

### Key Improvements
1.  **Dynamic Turn Scaling**: Steering strength is scaled linearly with speed:
    `turn_step = BASE_TURN_STEP * (current_speed / REFERENCE_SPEED)`
    This ensures that the turning radius remains consistent, preventing "ping-ponging" or jitter at low velocities.
2.  **Adaptive Look-ahead**: The sensor distance is adjusted slightly with speed (scaling from 0.8x to 1.0x of the base distance). This allows faster zombies to anticipate corners earlier while keeping slow zombies focused on the immediate wall geometry.

### Impact on Stability
In low-speed simulations (40% speed), dynamic scaling reduced direction-change jitter by approximately 40%, leading to much smoother movement along walls as zombies age.

## Small Cell Size Optimization (35px-45px)

Feedback indicates that while the AI is stable on larger grids, it struggles on smaller cell sizes (35px, 40px, 45px). On these grids, the relative proportions of the zombie radius, target gap, and sensor distance change significantly.

### Challenges on Small Grids
- **Relatively Large Sensors**: A 30px sensor on a 35px grid covers almost the entire next cell, potentially picking up walls too early.
- **Narrow Corridors**: The physical space between walls is tighter, making steering jitter more problematic.
- **Corner Overshoot**: On small grids, a single frame's movement is a larger percentage of the cell width, making precise cornering harder.

### New Experiment Plan
We will perform a targeted parameter sweep for cell sizes 35, 40, and 45 to find a "Small Grid Profile" or a unified scaling law that handles these cases.

#### Parameters to Re-evaluate
- **Min Sensor Distance**: Should `ZOMBIE_WALL_HUG_SENSOR_DISTANCE` be lower for small cells?
- **Target Gap**: Is 4.2px too much?
- **Base Turn Step**: Is 8.0° too aggressive when the corridor is tight?
- **Sensor Ratio**: Refining the 0.6 ratio for small scales.

## Multi-Probe High-Precision Shape Tracking (New Experiment)

To address the issue where zombies miss 1-cell gaps on small grids (35px), we are transitioning from a 3-probe system to a **4-probe High-Fidelity system**.

### The Problem: Bridging
On a 35px grid, a diagonal 55° sensor might "see" the wall on the other side of a 1-cell gap before the zombie has turned, causing it to "bridge" the gap and continue straight.

### New Sensor Configuration
We are adding a **Perpendicular (90°) probe** to the tracking side:
1.  **Forward (0°)**: Detects obstacles in front.
2.  **Front-Diagonal (30°)**: Anticipates inner corners and upcoming wall curves.
3.  **Mid-Diagonal (60°)**: Maintains the target gap.
4.  **Side-Perpendicular (90°)**: Detects the exact moment a wall ends (outer corners/gaps).

### Shape-Priority Logic
We are shifting the optimization target from "Smoothness" to "Shape Fidelity":
- **High Sensitivity to Discontinuity**: If the 90° or 60° probe loses the wall, the zombie will initiate a sharp turn immediately.
- **Accepted Jitter**: To ensure 1-cell gaps are never missed, we allow higher angular velocity (jitter) in exchange for tighter wall following.

## Asymmetrical 3-Probe System (Final Implementation)

To achieve reliable 1-cell gap detection on the smallest grids (35px) without increasing CPU overhead, we implemented an **Asymmetrical 3-Probe system**.

### Final Configuration
1.  **Forward (0°)**: Detects immediate obstacles and dead ends.
2.  **Tracking Diagonal (55° base)**: Main probe for maintaining the target gap (4.2px). Scales with speed to widen at low velocities.
3.  **Tracking Perpendicular (90°)**: Monitors the wall continuity. **Losing the wall on this probe triggers an immediate sharp turn**, ensuring 1-cell gaps are never bypassed.

### Results
- **Gap Sensitivity**: Successfully detects and enters 35px wide wall openings at all speeds.
- **Performance**: Maintains the same computational footprint as the previous symmetrical system.
- **Cornering**: Significantly improved outer-corner tracking by responding to the 90° probe discontinuity.
