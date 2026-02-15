# Zombie AI

## Variant Strategies

Zombie movement is strategy-driven (`movement_strategy` per instance):

- Normal (`zombie_normal_movement`)
  - Direct chase when player is in sight.
  - Wander otherwise.
- Tracker (`zombie_tracker_movement`)
  - Direct chase in sight range.
  - Footprint scent targeting when out of sight.
- Wall-hugger (`zombie_wall_hug_movement`)
  - Maintains side-gap from walls with probe-based steering.
  - Falls back to wander if no wall is detected for a while.
- Lineformer
  - Managed as train units (`LineformerTrainManager`).
  - Only head is a real zombie entity; followers are marker positions.
- Zombie dog
  - State-based behavior (`WANDER`, `CHARGE`, `CHASE`).

## Tracker Details

- Footprint search is throttled (not every frame).
- Uses near/far scent radius phases.
- Filters out footprints too close to current position.
- Uses straight-line reachability checks (wall blocking avoidance).
- If target is reached and no better target exists, retarget by freshness rules.

## Wall-Hugger Stability Tuning

- Probe length scales with cell size.
- Target gap tuned for diagonal probe geometry.
- Per-frame turn step tuned to balance straight stability and cornering.

## Lineformer Train Management

- New lineformers join nearby eligible trains.
- Train-target contention is resolved each frame.
- Merging requires proximity + history-gate conditions.
- If head disappears, train dissolves by respawning members sequentially.
- Marker movement follows sampled head history with interpolation.

## Spawn Ratio Selection

- `create_zombie()` selects variant by stage ratios:
  - `zombie_normal_ratio`
  - `zombie_tracker_ratio`
  - `zombie_wall_hugging_ratio`
  - `zombie_lineformer_ratio`
  - `zombie_dog_ratio`

## Congestion Mitigation for Trackers

To avoid over-stacking on the same footprint lane:

- Tracker -> wander fallback:
  - Count trackers by `(32px grid cell, 8-direction bin)`.
  - If the local lane count reaches threshold, force one tracker to wander.
- Wander -> tracker relock control:
  - After forced fallback, trackers ignore older footprints until relock delay elapses.

## Pitfall Interaction

- Zombies can fall and be removed when entering pitfall cells.
- Wander logic attempts pitfall avoidance; chase paths may still fall.
