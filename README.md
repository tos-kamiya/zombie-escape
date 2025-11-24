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

<img src="imgs/screenshot1.png" width="400">
<img src="imgs/screenshot2.png" width="400">

## Controls

-   **Player/Car Movement:** `W` / `↑` (Up), `A` / `←` (Left), `S` / `↓` (Down), `D` / `→` (Right)
-   **Enter Car:** Overlap the player with the car.
-   **Quit Game:** `ESC` key
-   **Restart:** `R` key (on Game Over/Clear screen)

## Game Rules

### Stages (new in 0.7.0)

At the title screen you can pick a stage:

- **Stage 1: Find the Car** — locate the car and drive out.
- **Stage 2: Fuel Run** — find a fuel can first, pick it up, then find the car and escape.

An objective reminder is shown at the top-left during play.

### Characters/Items

-   **Player:** A blue circle. Controlled with the WASD or arrow keys.
-   **Zombie:** A red circle. Will chase the player (or car) once detected.
    -   Zombies enter a direct pursuit mode when the player enters their line of sight (`ZOMBIE_SIGHT_RANGE`).
    -   When out of sight, the zombie's movement mode will randomly switch every certain time (moving horizontally/vertically only, side-to-side movement, random movement, etc.).
-   **Car:** A yellow rectangle. The player can enter by making contact with it.
    -   The car has durability. Durability decreases when colliding with internal walls or hitting zombies.
    -   If durability reaches 0, the car is destroyed, and the player is ejected.
    -   When the car is destroyed, a **new car will respawn** at a random location within the stage.
    -   After roughly 3 minutes of play, a small triangle near the player points toward the objective: fuel first (Stage 2 before pickup), car after fuel is collected (Stage 2), or car directly (Stage 1).
-   **Fuel Can (Stage 2):** A yellow jerrycan. Pick it up before driving the car.
-   **Walls:** Gray rectangles.
    -   **Outer Walls:** Walls surrounding the stage that are nearly indestructible. Each side has at least three openings (exits).
    -   **Inner Walls:** Walls randomly placed inside the building. Inner wall segments each have durability. **The player can break these walls** by repeatedly colliding with a segment to reduce its durability; when it reaches 0, the segment is destroyed and disappears. The car cannot break walls.

### Win/Lose Conditions

-   **Win Condition:** Escape the stage (level) boundaries while inside the car.
    - Stage 2 also requires that you have collected the fuel can before driving out.
-   **Lose Condition:**
    -   The player is touched by a zombie while *not* inside a car.
    -   (Note: In the current implementation, the game does not end immediately when the car is destroyed. The player can search for another car and continue trying to escape.)

## How to Run

**Requirements: Python 3.10 or higher**

Install using pipx:

```sh
pipx install git+https://github.com/tos-kamiya/zombie-escape
```

Alternatively, you can install using git and pip:
(Installing in a virtual environment is recommended)

```sh
git clone https://github.com/tos-kamiya/zombie-escape
cd zombie-escape
pip install .
```

Launch using the following command line:

```sh
zombie-escape
```

**An `.exe` file for Windows** is also available. You can download it from the [Releases page](https://github.com/tos-kamiya/zombie-escape/releases).

## License

This project is licensed under the MIT License - see the [LICENSE.txt](LICENSE.txt) file for details.

## Acknowledgements

Significant assistance for many technical implementation and documentation aspects of this game's development was received from Google's large language model, Gemini (accessed during development), and from OpenAI's GPT-5. This included generating Python/Pygame code, suggesting rule adjustments, providing debugging support, and creating this README. Their rapid coding capabilities and contributions to problem-solving are greatly appreciated.
