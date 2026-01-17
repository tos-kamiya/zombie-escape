"""Gameplay-related constants and helpers."""

from __future__ import annotations

# --- Survival stage settings ---
SURVIVAL_TIME_ACCEL_SUBSTEPS = 4
SURVIVAL_TIME_ACCEL_MAX_SUBSTEP = 1.0 / 30.0
SURVIVAL_FAKE_CLOCK_RATIO = 12.0  # 20 min -> 4 hr clock

# --- Survivor settings (Stage 4) ---
SURVIVOR_SPAWN_RATE = 0.07

# --- Flashlight settings ---
DEFAULT_FLASHLIGHT_SPAWN_COUNT = 2

# --- Zombie settings ---
ZOMBIE_SPAWN_DELAY_MS = 4000

# --- Car and fuel settings ---
CAR_HINT_DELAY_MS_DEFAULT = 300000

__all__ = [
    "SURVIVAL_TIME_ACCEL_SUBSTEPS",
    "SURVIVAL_TIME_ACCEL_MAX_SUBSTEP",
    "SURVIVAL_FAKE_CLOCK_RATIO",
    "SURVIVOR_SPAWN_RATE",
    "DEFAULT_FLASHLIGHT_SPAWN_COUNT",
    "ZOMBIE_SPAWN_DELAY_MS",
    "CAR_HINT_DELAY_MS_DEFAULT",
]
