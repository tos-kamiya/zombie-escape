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
