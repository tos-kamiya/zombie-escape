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
