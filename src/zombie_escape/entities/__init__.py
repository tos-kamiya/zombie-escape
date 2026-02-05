"""Sprite and entity definitions for zombie_escape."""

from __future__ import annotations

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

import pygame
from pygame import rect

from ..entities_constants import (
    FLASHLIGHT_HEIGHT,
    FLASHLIGHT_WIDTH,
    FUEL_CAN_HEIGHT,
    FUEL_CAN_WIDTH,
    SHOES_HEIGHT,
    SHOES_WIDTH,
)
from ..render_assets import (
    build_flashlight_surface,
    build_fuel_can_surface,
    build_shoes_surface,
)
from ..rng import get_rng
from ..screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH
from .collisions import spritecollideany_walls
from .walls import SteelBeam, Wall, RubbleWall
from .car import Car
from .player import Player
from .survivor import Survivor
from .zombie import Zombie

RNG = get_rng()


class Camera:
    def __init__(self: Self, width: int, height: int) -> None:
        self.camera = pygame.Rect(0, 0, width, height)
        self.width = width
        self.height = height

    def apply(self: Self, entity: pygame.sprite.Sprite) -> rect.Rect:
        return entity.rect.move(self.camera.topleft)

    def apply_rect(self: Self, rect: rect.Rect) -> rect.Rect:
        return rect.move(self.camera.topleft)

    def update(self: Self, target: pygame.sprite.Sprite) -> None:
        x = -target.rect.centerx + int(SCREEN_WIDTH / 2)
        y = -target.rect.centery + int(SCREEN_HEIGHT / 2)
        x = max(-(self.width - SCREEN_WIDTH), min(0, x))
        y = max(-(self.height - SCREEN_HEIGHT), min(0, y))
        self.camera = pygame.Rect(x, y, self.width, self.height)


def random_position_outside_building(level_width: int, level_height: int) -> tuple[int, int]:
    side = RNG.choice(["top", "bottom", "left", "right"])
    margin = 0
    if side == "top":
        x, y = RNG.randint(0, level_width), -margin
    elif side == "bottom":
        x, y = RNG.randint(0, level_width), level_height + margin
    elif side == "left":
        x, y = -margin, RNG.randint(0, level_height)
    else:
        x, y = level_width + margin, RNG.randint(0, level_height)
    return x, y


class FuelCan(pygame.sprite.Sprite):
    """Simple fuel can collectible used in Stage 2."""

    def __init__(self: Self, x: int, y: int) -> None:
        super().__init__()
        self.image = build_fuel_can_surface(FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT)
        self.rect = self.image.get_rect(center=(x, y))


class Flashlight(pygame.sprite.Sprite):
    """Flashlight pickup that expands the player's visible radius when collected."""

    def __init__(self: Self, x: int, y: int) -> None:
        super().__init__()
        self.image = build_flashlight_surface(FLASHLIGHT_WIDTH, FLASHLIGHT_HEIGHT)
        self.rect = self.image.get_rect(center=(x, y))


class Shoes(pygame.sprite.Sprite):
    """Shoes pickup that boosts the player's move speed when collected."""

    def __init__(self: Self, x: int, y: int) -> None:
        super().__init__()
        self.image = build_shoes_surface(SHOES_WIDTH, SHOES_HEIGHT)
        self.rect = self.image.get_rect(center=(x, y))


__all__ = [
    "Wall",
    "RubbleWall",
    "SteelBeam",
    "spritecollideany_walls",
    "Camera",
    "Player",
    "Survivor",
    "Zombie",
    "Car",
    "FuelCan",
    "Flashlight",
    "Shoes",
    "random_position_outside_building",
]
