# Carrier Bot and Material

This chapter defines the implemented `CarrierBot` variant and the passive
`Material` entity.

## Scope

- `CarrierBot` is a line-movement bot variant.
- `Material` is a carryable passive object.
- Shared line movement mechanics are reused via `BaseLineBot`.
- This system is separate from `TransportBot`.

## Terminology

- `Axis`: fixed move axis per bot instance (`x` or `y`).
- `Loaded`: bot currently carries one `Material`.
- `Unloaded`: bot does not carry material.

## `BaseLineBot` Responsibilities

`BaseLineBot` contains shared mechanics, not role-specific AI.

- Fixed-axis movement (`x`-axis or `y`-axis).
- Direction state (`-1` / `+1`) and reverse operation.
- Forward-cell computation.
- Shared move-block helpers (axis wall checks, overlap resolution).
- Shared wall-separation and position correction behavior.

Role-specific decisions stay in derived classes (`PatrolBot`, `CarrierBot`):

- When to reverse.
- Whether a terrain/hazard exception is allowed (e.g. flame-floor policy).
- Special interactions (carry/drop).

## `Material` Entity Design

`Material` is a dedicated entity and is not a robot subclass.

- No autonomous movement.
- On ground, it is represented as `layout.material_cells` and blocks humanoid
  movement like wall-type cells.
- Has carry state:
  - `carried_by: CarrierBot | None`
- Position rule:
  - If `carried_by is None`, stays at world position.
  - If carrying, follows carrier anchor position every update tick.

## `CarrierBot` State Machine

Working states:

- `UNLOADED`
- `LOADED`

`UNLOADED` tick behavior:

1. Move along axis.
2. If complete-overlap with a loadable `Material` occurs:
   - Attach that material (`carried_by = self`).
   - Reverse direction immediately.
3. If movement is blocked:
   - Reverse direction.

`LOADED` tick behavior:

1. Check forward movement.
2. If blocked:
   - Drop carried material.
   - Reverse direction.
3. Else:
   - Move forward while material follows.

Drop rules:

- Material drop uses cell-based placement, preferring safe cell centers near the
  bot.
- Placement avoids out-of-bounds/outside/outer-wall/pitfall/wall-overlap and
  occupied material cells.
- After drop, the same material is temporarily excluded from re-pickup until
  the carrier separates.

Constraints:

- One carrier holds at most one material.
- One material can be carried by at most one carrier.
- While carried, only the carrier collision is used.

## Spawn/Stage Data

- `Stage.carrier_bot_spawns`: `(cell_x, cell_y, axis, direction_sign)`
- `Stage.material_spawns`: `(cell_x, cell_y)`
- Spawn points are defined in cell-space and converted to cell centers.
- Stage validation checks coordinate bounds and carrier parameter validity.

## Collision and Terrain Policy

- Carrier movement blocks on walls, outside/outer-wall cells, pitfall cells, and
  relevant entity blockers.
- Grounded materials participate via `material_cells` for humanoid grid-blocking.

## Rendering/Layering

- `CarrierBot` renders in vehicle layer.
- Grounded `Material` renders in item layer.
- Carried material position is synced to carrier center.

## Notes

- `stage36` is configured as a verification stage for carrier/material behavior.
