# Stages 26-35 Additions

This page covers additions first appearing in Stages 26-35.

| Name | Image | First Appears | Notes |
| --- | --- | --- | --- |
| Empty Fuel Can | <img src="../imgs/exports/empty-fuel-can.png" width="80"> | Stage 26 | Pickup item used in stages where the empty fuel can appears. |
| Fuel Station | <img src="../imgs/exports/fuel-station.png" width="80"> | Stage 26 | Refills the empty fuel can in stages where the empty fuel can appears. |
| Zombie (Lineformer) | <img src="../imgs/exports/zombie-lineformer.png" width="80"> | Stage 27 | A zombie that likes to form lines. |
| Puddle | <img src="../imgs/exports/puddle.png" width="80"> | Stage 28 | Slows movement while you are on the puddle tile. |
| Spiky Houseplant | <img src="../imgs/exports/houseplant.png" width="80"> | Stage 28 | In its normal state, humanoids move more slowly on it. Zombies get trapped in it and remain as trapped threats on that tile. |
| Zombie Dog (Nimble) | <img src="../imgs/exports/zombie-dog-nimble.png" width="80"> | Stage 31 | Skittering zombie dog. |
| Zombie (Solitary) | <img src="../imgs/exports/zombie-solitary.png" width="80"> | Stage 34 | A zombie that avoids crowds and keeps to itself. |

## Fuel Rule Change (Stages with Empty Fuel Can)

In stages where the empty fuel can appears, fuel handling is different:

- Regular fuel-can stages: `Player -> fuel can -> car`
- Stages where the empty fuel can appears: `Player -> empty fuel can -> fuel station -> car`

You cannot skip the station in stages where the empty fuel can appears.
