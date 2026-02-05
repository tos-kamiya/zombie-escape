# Zombie Escape

The city is overrun with zombies!
You fled the horde, taking refuge in an abandoned factory.

Inside, it's a maze. They won't get in easily.
But you have no weapons. Night has fallen. The power's out, plunging the factory into darkness.

Your only tool: a single flashlight.
A car... somewhere inside... it's your only hope.

Pierce the darkness and find the car!
Then, escape this nightmare city!

## Overview

This game is a simple 2D top-down action game where the player aims to escape by finding and driving a car out of a large building infested with zombies. The player must evade zombies, break through walls to find a path, and then escape the building in a car.

<img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/screenshot1.png" width="400">
<img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/screenshot2.png" width="400">
<img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/screenshot3.png" width="400">
<img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/screenshot4.png" width="400">

## Controls

-   **Player/Car Movement:** `W` / `↑` (Up), `A` / `←` (Left), `S` / `↓` (Down), `D` / `→` (Right)
-   **Enter Car:** Overlap the player with the car.
-   **Pause:** `P`/Start or `ESC`/Select
-   **Quit Game:** `ESC`/Select (from pause)
-   **Restart:** `R` key (on Game Over/Clear screen)
-   **Window/Fullscreen:** `[` to shrink by one step (400x300), `]` to enlarge by one step, `F` to toggle fullscreen
-   **FPS Overlay:** Launch with `--show-fps` (implied by `--debug`)
-   **Time Acceleration:** Hold either `Shift` key or `R1` to run the entire world 4x faster; release to return to normal speed.

## Title Screen

### Stages

At the title screen you can pick a stage:

- **Stage 1: Find the Car** — you already start with fuel; find the car and escape.
- **Stage 2: Fuel Run** — you start with no fuel; find a fuel can first, pick it up, then find the car and escape.
- **Stage 3: Rescue Buddy** — same fuel hunt as Stage 2 (you begin empty) plus locate your buddy, pick them up with the car, then escape together.
- **Stage 4: Evacuate Survivors** — start fueled, find the car, gather survivors, and escape before zombies reach them. The stage includes extra parked cars; ramming one while driving fully repairs your current ride and adds five seats each time.
- **Stage 5: Survive Until Dawn** — every car is empty. Endure until sunrise while the horde presses in from every direction. Once dawn hits and outdoor zombies carbonize, walk out through an existing exterior gap to win; cars remain unusable.

Stages 6+ unlock after clearing Stages 1–5. On the title screen, use left/right to select later stages.
Open the Stage 6+ description: [docs/stages-6plus.md](docs/stages-6plus.md)

**Stage names are red until cleared** and turn white after at least one clear.

An objective reminder is shown at the top-left during play.

### Win/Lose Conditions

-   **Win Condition:** Escape the stage (level) boundaries while inside the car.
    - Stage 1 and Stage 4 follow the base rule: drive out of the building by car.
    - Stage 2 also requires that you have collected the fuel can before driving out.
    - Stage 3 requires meeting up with your buddy and escaping the building by car.
    - Stage 5 has no working cars; survive until dawn, then walk out through an exterior opening on foot.
-   **Lose Condition:**
    -   The player is touched by a zombie while *not* inside a car.
    -   In Stage 3, if your buddy is caught (when visible), it's game over.
    -   (Note: In the current implementation, the game does not end immediately when the car is destroyed. The player can search for another car and continue trying to escape.)

### Shared Seeds

The title screen also lets you enter a numeric **seed**. Type digits (or pass `--seed <number>` on the CLI) to lock the procedural layout, wall placement, and pickups; share that seed with a friend and you will both play the exact same stage even on different machines. The current seed is shown at the bottom right of the title screen and in-game HUD. Backspace reverts to an automatically generated value so you can quickly roll a fresh challenge.

## Settings Screen

Open **Settings** from the title to toggle gameplay assists:

-   **Footprints:** Leave breadcrumb trails so you can backtrack in the dark.
-   **Fast zombies:** Allow faster zombie variants; each zombie rolls a random speed between the normal and fast ranges.
-   **Car hint:** After a delay, show a small triangle pointing toward the fuel (Stage 2 before pickup) or the car.
-   **Steel beams:** Adds tougher single-cell obstacles (about 5% density) that block movement.

## Game Rules

### Characters/Items

#### Characters

<table>
  <colgroup>
    <col style="width:20%">
    <col>
    <col>
  </colgroup>
  <thead>
    <tr>
      <th>Name</th>
      <th>Image</th>
      <th>Notes</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Player</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/player.png" width="64"></td>
      <td>Blue circle with small hands; controlled with WASD/arrow keys. When carrying fuel, a tiny yellow square appears near the sprite.</td>
    </tr>
    <tr>
      <td>Zombie (Normal)</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/zombie-normal.png" width="64"></td>
      <td>Chases the player once detected; out of sight it periodically switches movement modes.</td>
    </tr>
    <tr>
      <td>Car</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/car.png" width="64"></td>
      <td>Driveable escape vehicle; touch to enter. Durability drops from wall hits and running over zombies; if it reaches 0, the car breaks. Capacity starts at five. Ramming a parked car while driving restores health and adds +5 capacity. After ~5 minutes, a small triangle points to the current objective.</td>
    </tr>
    <tr>
      <td>Buddy (Stage 3)</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/buddy.png" width="64"></td>
      <td>Green survivor you can rescue; zombies only target them on-screen and off-screen catches just respawn them. Touch on foot to follow (70% speed), touch while driving to pick up. Helps chip away at walls you bash.</td>
    </tr>
    <tr>
      <td>Survivors (Stage 4)</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/survivor.png" width="64"></td>
      <td>Civilians to evacuate by car; they idle until approached, then follow at ~1/3 speed. On-screen zombie contact converts them. If you exceed the car's capacity, the car is damaged and everyone disembarks.</td>
    </tr>
  </tbody>
</table>

#### Items

<table>
  <colgroup>
    <col style="width:20%">
    <col>
    <col>
  </colgroup>
  <thead>
    <tr>
      <th>Name</th>
      <th>Image</th>
      <th>Notes</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Flashlight</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/flashlight.png" width="64"></td>
      <td>Each pickup expands your visible radius by about 20%.</td>
    </tr>
    <tr>
      <td>Fuel Can (Stages 2 & 3)</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/fuel.png" width="64"></td>
      <td>Appears only in stages that begin without fuel; pick it up to unlock driving.</td>
    </tr>
    <tr>
      <td>Steel Beam (optional)</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/steel-beam.png" width="64"></td>
      <td>Striped obstacle with the same collision as inner walls, but 1.5x durability. Can also appear after an inner wall is destroyed.</td>
    </tr>
  </tbody>
</table>

#### Environment

<table>
  <colgroup>
    <col style="width:20%">
    <col>
    <col>
  </colgroup>
  <thead>
    <tr>
      <th>Name</th>
      <th>Image</th>
      <th>Notes</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Outer Wall</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/wall-outer.png" width="64"></td>
      <td>Gray perimeter walls that are nearly indestructible; each side has a single opening (exit).</td>
    </tr>
    <tr>
      <td>Inner Wall</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/wall-inner.png" width="64"></td>
      <td>Beige interior walls with durability. The player can break them by repeated collisions; zombies wear them down slowly; the car cannot break them.</td>
    </tr>
  </tbody>
</table>

## How to Run

**Requirements: Python 3.10 or higher**

Install using pipx:

```sh
pipx install zombie-escape
```

Alternatively, you can install using pip in a virtual environment:

```sh
pip install zombie-escape
```

Launch using the following command line:

```sh
zombie-escape
```

## License

This project is licensed under the MIT License - see the [LICENSE.txt](LICENSE.txt) file for details.

This project depends on pygame-ce (repository: `https://github.com/pygame-community/pygame-ce`), which is licensed under GNU LGPL version 2.1.

The bundled Silkscreen-Regular.ttf font follows the license terms of its original distribution.
Please refer to the upstream website for details: https://fonts.google.com/specimen/Silkscreen

The bundled misaki_gothic.ttf font (Misaki font by Num Kadoma) follows the license terms provided by Little Limit.
Please refer to the official site for details: https://littlelimit.net/misaki.htm

## Acknowledgements

Significant assistance for many technical implementation and documentation aspects of this game's development was received from Google's large language model, Gemini (accessed during development), and from OpenAI's GPT-5. This included generating Python/Pygame code, suggesting rule adjustments, providing debugging support, and creating this README. Their rapid coding capabilities and contributions to problem-solving are greatly appreciated.

Thanks to Jason Kottke, the author of the Silkscreen-Regular.ttf font used in the game.
Thanks to Num Kadoma, the author of the Misaki font (misaki_gothic.ttf) distributed via Little Limit.
