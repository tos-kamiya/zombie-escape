# Entities

## Core Non-Zombie Entities

- `Player`: primary controlled entity when not in car.
- `Car`: alternate control target with health and passenger behavior.
- `Survivor`: rescue NPC; `is_buddy=True` marks buddy role.
- `PatrolBot`: moving hazard/support object with programmable turning behavior.
- `Wall` / `RubbleWall` / `SteelBeam`: collision and destruction-capable obstacles.
- Item entities: `FuelCan`, `EmptyFuelCan`, `FuelStation`, `Flashlight`, `Shoes`.
- Trap entity: `SpikyPlant`.

## Zombie Entities

- `Zombie`: variant-driven movement via strategy function.
- `ZombieDog`: directional sprite set with head-focused collision behavior.
- Both support durability + decay over time.

## Shared Rules

- 16-direction facing (22.5-degree steps) for character-like entities.
- Human-like sprites share cached directional textures.
- Player and buddy render with arm markers; survivors/zombies do not.
- Buddy can damage interior walls/steel beams when colliding.
- Player wall collision can split wall damage across overlapping collided walls
  in the same contact frame.
- Off-screen survivor/buddy zombie contact triggers respawn behavior.
- Car and patrol bot wall-overlap resolution uses shared
  `separate_circle_from_walls(...)` from `entities/movement.py`.
  - Car parameters prioritize visible bounce (`scale=2.1`,
    `first_extra_clearance=6.0`) and fall back to `last_safe_pos` if still stuck.
  - Patrol bot parameters prioritize conservative correction (`scale=1.0`,
    no extra clearance) and fall back to its current position if still stuck.

## Footprints

- Stored as pixel coordinates plus visibility/lifetime fields.
- Tracking zombies can use invisible footprints for scent-following.
- Footprint generation is disabled while player is in car and while player is
  inside puddle cells.
- Entering those no-footprint segments is treated as trail-segment
  break for tracker progression.

## PatrolBot

- Circular body, speed at half of player base speed.
- Changes direction on wall/pitfall/bot/car collision.
- Reverses at outside area boundaries.
- Can stun/slow interactions via electrified-cell updates.
- While the bot is stopped due to overlap with player/humanoids, the player can set
  its direction only after a neutral-input frame and then a directional input.
- Turn pattern cycles through right/left blocks (`TF`, `TTFF`, ...).

## Transport Bot (INPROGRESS)

- New transport-only vehicle entity (temporary visual: plain white rectangle).
- Boarding capacity is exactly one passenger.
- Boardable targets are `Player`, `Buddy`, and `Survivor` only.
- Zombies cannot board.
- Activation is automatic: while stopped, if a boardable target enters the
  center activation area, it starts (no explicit player confirm required).
- On start, doors close and passenger lock is taken before movement.
- Movement path is a stage-defined polyline in cell coordinates and runs in
  round-trip mode.
- Bot can wait at both polyline endpoints before the next run.
- While moving, if the forward path is blocked by wall or pitfall, it reverses
  travel direction.
- While moving, the bot keeps moving even when colliding with outside entities;
  outside entities are pushed away using patrol-bot-like push behavior.
- While moving, onboard passenger has no interaction with outside world
  (collision/combat/rescue/infection/hazard interaction disabled).
- At destination endpoint, doors open and passenger is released, then normal
  interactions resume.

## Moving Floor

- Four fixed directions (`^`, `v`, `<`, `>`).
- Affects player, survivors, buddy, zombies, dogs, patrol bots, and cars.
- Applies additive velocity; does not cancel player input or AI decisions.
- Can be specified by explicit cells and/or rectangular zones.

## Spiky Plant

- Fixed trap centered in a cell.
- Captures zombies/zombie dogs into immobile trapped variants.
- Trapped entities remain threats and continue decay.
- Humanoids/cars can pass through but get heavy speed penalty.
- Car contact destroys the plant and applies minor car damage.

## Puddles

- Terrain-only slow tile (`w`), not a sprite.
- Applies movement speed factor while on puddle cells.
- Spiky plant slow has higher priority than puddle slow.
- In gameplay render, visualized with animated ripple-ring tiles.
- In overview render, visualized as a simple circle marker for readability.
- Puddle cells suppress footprint recording, so long puddle crossings
  can create scent gaps for tracker zombies.

## Floor Ruin Dressing

- This is a floor-render decoration feature, not an entity type.
- Visuals (`dust`, `debris`, `screw/metal bits`) are documented in
  `docs/design/rendering.md`.
- Stage-number barcode marks on normal/fall-spawn floor tiles are part of the same
  visual-only floor dressing layer.
- Scope is visual-only; no collision, movement, or gameplay-state behavior
  changes.
