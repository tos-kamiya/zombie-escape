from __future__ import annotations

import math
import pygame

from ..entities_constants import (
    HOUSEPLANT_HEALTH,
    HOUSEPLANT_RADIUS,
    HOUSEPLANT_COLLISION_RADIUS,
)

class SpikyHouseplant(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int):
        super().__init__()
        self.radius = HOUSEPLANT_RADIUS
        self.collision_radius = HOUSEPLANT_COLLISION_RADIUS
        self.health = HOUSEPLANT_HEALTH
        self.max_health = HOUSEPLANT_HEALTH
        
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        # Main body
        pygame.draw.circle(
            self.image,
            (30, 120, 30), # Darker green
            (self.radius, self.radius),
            self.radius - 2
        )
        # Spikes (just some lines for now)
        for i in range(8):
            angle = i * (math.tau / 8)
            start_dist = self.radius - 4
            end_dist = self.radius
            start_p = (
                self.radius + math.cos(angle) * start_dist,
                self.radius + math.sin(angle) * start_dist
            )
            end_p = (
                self.radius + math.cos(angle) * end_dist,
                self.radius + math.sin(angle) * end_dist
            )
            pygame.draw.line(self.image, (150, 255, 150), start_p, end_p, 2)

        self.rect = self.image.get_rect(center=(x, y))
        self.x = float(x)
        self.y = float(y)

    def _take_damage(self, amount: int = 1) -> None:
        self.health -= amount
        if self.health <= 0:
            self.kill()
