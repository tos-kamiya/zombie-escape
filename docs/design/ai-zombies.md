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
  - When `friendliness_max > 0`, can run friendly-orbit behavior and later fall back to feral states.

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
- Target selection rules:
  - Non-lineformer targets are preferred when available.
  - ID-order gating (`target_id < self_id`) is applied only when the candidate target is another lineformer (to avoid cyclic lineformer targeting while keeping normal-zombie targeting available).
- Merge behavior:
  - When a lineformer-targeting train reaches the tail of a train that is targeting a non-lineformer, the source train is absorbed as a whole (head + all markers) into the destination train.
- Contact response:
  - When a lineformer head physically overlaps its current target, it applies a short repel movement away from the target instead of staying pressed against it.

## Spawn Ratio Selection

- `create_zombie()` selects variant by stage ratios:
  - `zombie_normal_ratio`
  - `zombie_tracker_ratio`
  - `zombie_wall_hugging_ratio`
  - `zombie_lineformer_ratio`
  - `zombie_dog_ratio`
- Nimble dog spawn share is controlled by `zombie_nimble_dog_ratio` (applied only when dog variant is chosen).

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

## [INPROGRESS] Loner Zombie Design

This section describes a planned zombie variant, `loner`. It is design-only and not yet implemented.

### Behavior Spec

- Baseline behavior: stay still.
- Evaluation cadence: every 10 frames.
- Observation area: 5x5 neighborhood centered on self.
  - Directional counting excludes diagonal-equal offsets (`|dx| == |dy|`), which effectively drops the 4 corner tiles.
  - Resulting counted set size is 16 tiles (from the 21-tile 5x5-minus-corners set).
- Count target set: standard zombie entities only.
  - Excludes lineformer markers for performance and behavior simplicity.
  - Excludes self.
- Direction choice:
  - Count zombies in `up/down/left/right`.
  - Move 1 tile toward the direction(s) with the smallest count.
  - If tied, pick randomly.
- Last-direction suppression:
  - Keep `last_move_dir`.
  - When multiple minimum-count candidates exist, remove `last_move_dir` from the candidate set once.
  - If removal would make the set empty, restore the original candidates and pick randomly.
- Blocked move:
  - If chosen direction is not passable, do not move this cycle.

### Integration Plan

- Add a new zombie kind: `LONER`.
- Add a dedicated movement strategy function (do not merge into existing normal/tracker/wall-hugger logic).
- Keep directional counting as a small pure helper to simplify unit testing and tuning.
- Add stage ratio support for loner spawn selection (name to be finalized at implementation time).
