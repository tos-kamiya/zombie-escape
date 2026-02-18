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

**Keyboard/Gamepad**

-   **Player/Car Movement:** `W` / `↑` (Up), `A` / `←` (Left), `S` / `↓` (Down), `D` / `→` (Right)
-   **Enter Car:** Overlap the player with the car.
-   **Pause:** `P`/Start or `ESC`/Select
-   **Quit Game:** `ESC`/Select (from pause)
-   **Restart:** `R` key (on Game Over/Clear screen)
-   **Window/Fullscreen:** `[` to shrink by one step (400x300), `]` to enlarge by one step, `F` to toggle fullscreen
    -   After any of these operations, gameplay is forced into pause so input/focus state stays explicit.
-   **FPS Overlay:** Launch with `--show-fps` (implied by `--debug`)
-   **Time Acceleration:** Hold either `Shift` key or `R1` to run the entire world 4x faster; release to return to normal speed.

**Mouse**

-   **Gameplay** While holding left mouse button, the player moves toward the cursor.
    -   While holding left mouse button over the player character, the whole game runs at 4x speed.
    -   Moving the cursor into a corner hotspot triangle pauses the game.
    -   Resizing the OS window by mouse drag also forces gameplay pause.
-   **Title/Settings/etc.** Select items by releasing left mouse button.

## Title Screen

### Stages

At the title screen you can pick a stage:

- **Stage 1: Find the Car** — find the car and escape.
- **Stage 2: Fuel Run** — you start with no fuel; find a fuel can first, pick it up, then find the car and escape.
- **Stage 3: Rescue Buddy** — similarly, find fuel, locate your buddy, pick them up with the car, and escape together.
- **Stage 4: Evacuate Survivors** — find the car, gather survivors, and escape before zombies reach them. The stage has multiple parked cars; ramming one while driving adds +5 capacity.
- **Stage 5: Survive Until Dawn** — cars are unusable. Survive until sunrise, then leave on foot through an existing exterior opening.

Stage pages unlock progressively:

- Stages 1-5 are always available.
- Stages 6-15 unlock after clearing all Stages 1-5.
- Stages 16-25 unlock after clearing at least 5 stages on the Stages 6-15 page.
- For later pages, the same rule repeats: clear at least 5 stages on the current page to unlock the next page.

If fewer than 5 stages are cleared on a page (except page 1), the next page remains locked.
On the title screen, use left/right to switch unlocked pages.

**Stage names are red until cleared** and turn white after at least one clear. Cleared stage names also show icons for characters/items that appear in that stage.

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
      <td>Teal-blue survivor you can rescue; zombies only target them on-screen and off-screen catches just respawn them. Touch on foot to follow (70% speed), touch while driving to pick up. Helps chip away at walls you bash.</td>
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
