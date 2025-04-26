# Zombie Escape

## Overview

This game is a simple 2D top-down action game where the player aims to escape by finding and driving a car out of a large building infested with zombies. The player must evade zombies, break through walls to find a path, and then escape the building in a car.

## Controls

-   **Player Movement:** `W` / `↑` (Up), `A` / `←` (Left), `S` / `↓` (Down), `D` / `→` (Right)
-   **Enter Car:**  Overlap the player with the car.
-   **Drive Car:** (While in the car) `W` / `↑` (Forward), `A` / `←` (Turn Left), `S` / `↓` (Reverse), `D` / `→` (Turn Right)
-   **Quit Game:** `ESC` key
-   **Restart:** `R` key (on Game Over/Clear screen)

## Game Rules

### Elements

-   **Player:** A blue circle. Controlled with the WASD or arrow keys.
-   **Zombie:** A red circle. Will chase the player (or car) once detected.
    -   Zombies enter a direct pursuit mode when the player enters their line of sight (`ZOMBIE_SIGHT_RANGE`).
    -   When out of sight, the zombie's movement mode will randomly switch every certain time (moving horizontally/vertically only, side-to-side movement, random movement, etc.).
-   **Car:** A yellow rectangle. The player can enter by making contact with it.
    -   The car has durability. Durability decreases when colliding with internal walls or hitting zombies.
    -   If durability reaches 0, the car is destroyed, and the player is ejected.
    -   When the car is destroyed, a **new car will respawn** at a random location within the stage.
-   **Walls:** Gray rectangles.
    -   **Outer Walls:** Walls surrounding the stage that are nearly indestructible.  Each side has at least three openings (exits).
    -   **Inner Walls:** Walls randomly placed inside the building. Consist of short segments.

### Win/Lose Conditions

-   **Win Condition:** Escape the stage (level) while inside the car, by leaving the boundaries of the stage.
-   **Lose Condition:**
    -   The player is touched by a zombie while *not* inside a car.
    -   (Note: In the current implementation, the game does not end immediately when the car is destroyed.  The player can search for another car and continue trying to escape.)

### Special Rules

-   **Limited Visibility:** The player (or car they are in) can only see within a certain range around them.
    -   The central area is clearly visible (`FOV_RADIUS`).
    -   A slightly wider area around that (`FOV_RADIUS * FOV_RADIUS_SOFT_FACTOR`) is dimly visible.
    -   Anything beyond that is completely invisible.
-   **Wall Breaking:** Repeatedly colliding with a segment of an inner wall will reduce its durability. When durability reaches 0, the segment will be destroyed and disappear. The car cannot break walls.
-   **Scrolling:** The stage is larger than the screen, and the screen will scroll to follow the player (or car). Scrolling will stop when approaching the edge of the map.

## How to Run

Install using pipx:

```sh
pipx install git+https://github.com/tos-kamiya/zombie-escape
```

Alternatively, you can install using git and pip:

```sh
git clone https://github.com/tos-kamiya/zombie-escape
cd zombie-escape
pip install .
```

Launch using the following command line:

```sh
zombie-escape
```

## Acknowledgements

Significant assistance for many technical implementation and documentation aspects of this game's development was received from Google's large language model, Gemini (accessed during development). This included generating Python/Pygame code, suggesting rule adjustments, providing debugging support, and creating this README. Its rapid coding capabilities and contributions to problem-solving are greatly appreciated.
