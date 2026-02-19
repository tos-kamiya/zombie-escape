# Entities

## Core Non-Zombie Entities

- `Player`: primary controlled entity when not in car.
- `Car`: alternate control target with health and passenger behavior.
- `Survivor`: rescue NPC; `is_buddy=True` marks buddy role.
- `PatrolBot`: moving hazard/support object with programmable turning behavior.
- `Wall` / `RubbleWall` / `SteelBeam`: collision and destruction-capable obstacles.
- Item entities: `FuelCan`, `EmptyFuelCan`, `FuelStation`, `Flashlight`, `Shoes`.
- Trap entity: `SpikyHouseplant`.

## Zombie Entities

- `Zombie`: variant-driven movement via strategy function.
- `ZombieDog`: directional sprite set with head-focused collision behavior.
- Both support durability + decay over time.

## Shared Rules

- 16-direction facing (22.5-degree steps) for character-like entities.
- Human-like sprites share cached directional textures.
- Player and buddy render with arm markers; survivors/zombies do not.
- Buddy can damage interior walls/steel beams when colliding.
- Player wall collision applies damage to only the first detected wall per contact.
- Off-screen survivor/buddy zombie contact triggers respawn behavior.

## Footprints

- Stored as pixel coordinates plus visibility/lifetime fields.
- Tracking zombies can use invisible footprints for scent-following.

## PatrolBot

- Circular body, speed at half of player base speed.
- Changes direction on wall/pitfall/bot/car collision.
- Reverses at outside area boundaries.
- Can stun/slow interactions via electrified-cell updates.
- While the bot is stopped due to overlap with player/humanoids, the player can set
  its direction only after a neutral-input frame and then a directional input.
- Turn pattern cycles through right/left blocks (`TF`, `TTFF`, ...).

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
- Houseplant slow has higher priority than puddle slow.
- Visualized with animated ripple rings in normal and overview renders.
