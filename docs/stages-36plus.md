# Stages 36+ Notes

This page summarizes notes for Stage 36 and later.

## Stages

- **Stage 36: Material Warehouse**
- **Stage 37: Robots**
- **Stage 38: The Pursuers**
- **Stage 39: Restricted Zone**
- **Stage 40: Survival Odds**

## Character, Item, and Terrain Notes

| Name | Image | First Appears | Notes |
| --- | --- | --- | --- |
| Carrier Bot | <img src="../imgs/exports/carrier-bot.png" width="80"> | Stage 36 | A line-based robot that carries and drops materials while moving. |
| Material | <img src="../imgs/exports/material.png" width="80"> | Stage 36 | Carryable object handled by carrier bots. It also works as a collision obstacle. |
| Zombie Dog (Tracker) | <img src="../imgs/exports/zombie-dog-tracker.png" width="80"> | Stage 38 | A tracker dog variant that follows scent trails and closes in persistently. |

## Stage 40 Rule Note (Buddy + Endurance)

Stage 40 is the first stage that combines a buddy requirement with an endurance objective.

- Win:
  - No usable car: survive until dawn first.
  - After dawn, escape on foot through an exterior opening while linked up with your colleagues.
    (Internal check: `buddy_onboard + nearby_following_buddies >= buddy_required_count`.)
- Lose:
  - Same base lose rule as other stages: player contact with a zombie.
  - Buddy-stage lose rule also applies: if a buddy is caught while visible, it is game over.

## Stage 40 Strategy Hint (Spoilers)

**[SPOILER]** The following section contains solution hints. If you want to solve Stage 40 on your own, stop reading here.

### Layout Reading

- The center of the floor forms a `4x4` grid partitioned by fire-floor rows and puddle columns.
- Each grid cell has a fall-spawn zone at its center, which makes moving while escorting colleagues much riskier.
- The concave ("notch") regions at the top and bottom edges can be used to align patrol bots into stable up/down routes.

### Constraints Implied by the Layout

- Player:
  - Staying outside the `4x4` grid is the safer default.
  - To enter the inside area, you effectively need row-direction travel (left/right).
- Patrol bots:
  - If you change bot direction so it turns back at the notch shape, it can be made to shuttle in column-direction travel (up/down).

### Strategy

- Keep patrol bots shuttling, and when a zombie appears from a fall-spawn zone inside the grid, stop a passing patrol bot near that lane and use its electric stun/damage to handle the zombie.

### Intended Solution Pattern

1. Set up patrol bots so each grid column has an up/down shuttle.
2. Maintain that stabilized state and survive until dawn.
3. After dawn, merge with colleagues one by one.
4. Keep merged status and exit on foot through an outer opening.
