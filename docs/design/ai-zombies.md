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
- Solitary (`zombie_solitary_movement`, internal key: `solitary`)
  - Uses a 10-frame commit cycle.
  - Compares local zombie counts in 3-cell side bands (up/down/left/right) around its tile and moves toward lower-density sides.
  - Can move in 8 directions when both axes have a lower-density side.
  - Excludes trapped zombies and zombie dogs from its local counting.
  - Does not switch to direct chase; player context is treated as another local-spacing input.
- Zombie dog
  - Sub-variants: `normal`, `nimble`, `tracker`.
  - State-based behavior (`WANDER`, `CHARGE`, `CHASE`) for normal/nimble variants.
  - Charge start includes a short windup (face player direction, then pause for 2 frames).

## Tracker Details

- Footprint search is throttled (not every frame).
- Uses near/far scent radius phases.
- Filters out footprints too close to current position.
- Uses straight-line reachability checks (wall blocking avoidance).
- If target is reached and no better target exists, retarget by freshness rules.

## Tracker Zombie Dog

- Dog sub-variant `tracker` follows footprints while the player is out of sight.
- Tracker dog has a nose-line visual marker for identification (same style family as tracker zombie).
- Trail-loss and re-lock behavior matches tracker zombies:
  - same loss timeout progression rule,
  - same boundary-time based re-lock gate (`time > ignore_boundary`),
  - no extra fixed re-lock delay window in current implementation.
- On player sight, tracker dog switches to `CHARGE`.
- Tracker dog disables `CHASE` (no dog-pack zombie chasing).
- Tracker dog sight range is between tracker-zombie sight and normal dog sight.
- Tracker dog uses normal dog charge distance/cooldown.
- Tracker dog footprint-follow movement speed is `1.2x` patrol speed.

## Tracker Loss and Trail Gap Behavior
- Goal: prevent tracker zombies from permanently stacking at the latest footprint
  when footprint generation stops (for example, while player is in car).

Tracker loss rule (out-of-sight mode for tracker zombies and tracker dogs):

- Trackers treat the currently targeted footprint time as the "progress point".
- If no footprint newer than that progress point is found for a continuous timeout
  window, the tracker marks the trail as lost.
- On loss, the tracker drops active target and switches to wander behavior.
- When entering wander, if the player is close, the initial wander heading is
  nudged toward the player (uses dedicated range constants for zombie and dog).

Re-acquisition boundary rule:

- On loss, tracker stores an ignore boundary using the last tracked footprint
  timestamp (not current game time).
- Future scent scans must ignore footprints with `time <= ignore_boundary`.
- Only footprints with `time > ignore_boundary` can be used for re-lock.
- Current implementation does not apply an additional fixed re-lock delay window;
  boundary-time filtering is the active gate.
- This allows accidental re-acquisition of trail points that are ahead of the
  broken segment, while permanently excluding already-lost older points.

Puddle interaction with footprints:

- While the player is inside puddle cells, footprint recording is disabled.
- Entering a no-footprint segment (in-car or puddle) breaks the continuous trail
  segment for tracker progression purposes.
- As a result, crossing consecutive puddle cells can naturally cause trackers to
  lose the trail unless they later discover a newer post-gap footprint.

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
  - `zombie_solitary_ratio` (solitary)
  - `zombie_dog_ratio`
- Dog sub-variant shares are controlled by:
  - `zombie_nimble_dog_ratio`
  - `zombie_tracker_dog_ratio`
  - Both are applied only when dog variant is chosen.

## Pitfall Interaction

- Zombies can fall and be removed when entering pitfall cells.
- Wander logic attempts pitfall avoidance; chase paths may still fall.

## Solitary Notes

- Decision cadence is fixed at 10 frames; the chosen move vector is committed for that window.
- Local counting is based on a tile window around the solitary zombie and currently uses:
  - up-side cells: immediate upper row (`y-1`, `x-1..x+1`)
  - down-side cells: immediate lower row (`y+1`, `x-1..x+1`)
  - left-side cells: immediate left column (`x-1`, `y-1..y+1`)
  - right-side cells: immediate right column (`x+1`, `y-1..y+1`)
- Counting weights:
  - nearby zombie (non-trapped, non-dog): weight `3`
  - player context (player position, or active car position while in-car): weight `1`
- Movement choice:
  - Y axis: move toward the side with fewer zombies (`up` or `down`) if counts differ.
  - X axis: move toward the side with fewer zombies (`left` or `right`) if counts differ.
  - If both axes are chosen, move diagonally (8-direction support).
  - If both axes are tied, stay still.
- Anti-oscillation:
  - Immediate full reversal of the last committed move is suppressed.
- Spatial lookup:
  - Solitary uses spatial-index cell-window querying (`query_cells`) instead of radius querying.
