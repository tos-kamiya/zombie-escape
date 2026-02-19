from __future__ import annotations

import math

import pygame

from ..entities_constants import (
    SPIKY_PLANT_COLLISION_RADIUS,
    SPIKY_PLANT_HEALTH,
    SPIKY_PLANT_RADIUS,
)
from ..render_constants import (
    ENTITY_SHADOW_RADIUS_MULT,
    SPIKY_PLANT_BODY_COLOR,
    SPIKY_PLANT_SPIKE_COLOR,
)


class SpikyPlant(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int):
        super().__init__()
        self.radius = SPIKY_PLANT_RADIUS
        self.collision_radius = SPIKY_PLANT_COLLISION_RADIUS
        self.shadow_radius = max(
            1, int(self.collision_radius * ENTITY_SHADOW_RADIUS_MULT)
        )
        self.shadow_offset_scale = 1.0
        self.health = SPIKY_PLANT_HEALTH
        self.max_health = SPIKY_PLANT_HEALTH

        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            self.image,
            SPIKY_PLANT_BODY_COLOR,
            (self.radius, self.radius),
            self.radius - 2,
        )
        for i in range(8):
            angle = i * (math.tau / 8)
            start_dist = self.radius - 4
            end_dist = self.radius
            start_p = (
                self.radius + math.cos(angle) * start_dist,
                self.radius + math.sin(angle) * start_dist,
            )
            end_p = (
                self.radius + math.cos(angle) * end_dist,
                self.radius + math.sin(angle) * end_dist,
            )
            pygame.draw.line(self.image, SPIKY_PLANT_SPIKE_COLOR, start_p, end_p, 2)

        self.rect = self.image.get_rect(center=(x, y))
        self.x = float(x)
        self.y = float(y)

    def _take_damage(self, amount: int = 1) -> None:
        self.health -= amount
        if self.health <= 0:
            self.kill()

__all__ = ["SpikyPlant"]
