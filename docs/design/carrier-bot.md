# Carrier Bot and Material (INPROGRESS)

Status: `INPROGRESS`

This chapter defines the planned `CarrierBot` variant and the new passive
`Material` entity.

## Scope

- Introduce `CarrierBot` as a line-movement bot variant.
- Introduce `Material` as a carryable passive object.
- Reuse shared line-movement mechanics from a base class/mixin (working name:
  `BaseLineBot`).
- Keep this design separate from existing transport-bot features.

## Terminology

- `Axis`: fixed move axis per bot instance (`x` or `y`).
- `Forward cell`: one cell in the current facing direction along the assigned
  axis.
- `Loaded`: bot currently carries one `Material`.
- `Unloaded`: bot does not carry material.

## `BaseLineBot` Responsibilities

`BaseLineBot` should contain common movement mechanics, not role-specific AI.

- Fixed-axis movement (`x`-axis or `y`-axis).
- Direction state (`-1` / `+1`) and reverse operation.
- Forward-cell computation.
- Shared move-block checks:
  - Collision/repulsion occupancy checks.
  - Non-enterable terrain checks (puddle/pitfall policy can be configured).
- Shared wall-separation and position correction behavior.

Role-specific decisions stay in derived classes (`PatrolBot`, `CarrierBot`):

- When to reverse.
- Whether a terrain/hazard exception is allowed (e.g. flame-floor policy).
- Special interactions (carry/drop).

## `Material` Entity Design

`Material` is a dedicated entity and is not a robot subclass.

- No autonomous movement.
- Occupies space for collision/repulsion (other characters should not overlap).
- Has carry state:
  - `carried_by: CarrierBot | None`
- Position rule:
  - If `carried_by is None`, stays at world position.
  - If carrying, follows carrier anchor position every update tick.

Optional future extensions (out of scope now):

- Push/pull by player.
- Burnable/breakable material variants.

## `CarrierBot` State Machine

Working states:

- `UNLOADED`
- `LOADED`

`UNLOADED` tick behavior:

1. Check forward cell.
2. If a `Material` is directly ahead and loadable:
   - Attach that material (`carried_by = self`).
   - Reverse direction immediately.
3. Else if forward movement is blocked:
   - Reverse direction.
4. Else:
   - Move forward one step according to speed.

`LOADED` tick behavior:

1. Check forward movement.
2. If blocked:
   - Drop carried material at current location (or nearest valid non-overlap
     spot; exact drop resolution TBD).
   - Reverse direction.
3. Else:
   - Move forward while material follows.

Constraints:

- One carrier holds at most one material.
- One material can be carried by at most one carrier.
- Carrier and carried material should be treated as one moving unit for overlap
  with third parties.

## Spawn/Stage Data (Planned)

- `CarrierBot` spawn should include:
  - Position
  - Axis (`x`/`y`)
  - Initial direction (`-1`/`+1`)
- `Material` spawn list should be explicit in stage data.
- Stage authoring guideline:
  - Place materials on the active lane where carrier patrols.

## Collision and Terrain Policy (Planned)

Shared by line bots unless overridden:

- Repulsion: no overlap with solid entities.
- Non-enterable terrain: should include pitfall; puddle policy remains
  configurable and must be made explicit during implementation.
- Hazard entry (e.g. flame floor) should be controlled by bot-role policy, not
  hardcoded in `BaseLineBot`.

## Rendering/Layering (Planned)

- `CarrierBot` layer should remain compatible with existing bot layers.
- Carried material should render visually attached to carrier.
- Dropped material returns to normal entity layer ordering.

## Open Items

- Decide final class name: `BaseLineBot` vs `LineBotBase`.
- Decide exact drop placement fallback when current cell is invalid.
- Confirm puddle entry policy for bots (blocked or slow-only).
- Confirm whether player can interact with `Material` directly.

