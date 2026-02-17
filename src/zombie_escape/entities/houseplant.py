from __future__ import annotations

import math
import pygame

from ..entities_constants import (
    HOUSEPLANT_HEALTH,
    HOUSEPLANT_COLLISION_RADIUS,
    HOUSEPLANT_RADIUS,
)
from ..render_constants import HOUSEPLANT_BODY_COLOR, HOUSEPLANT_SPIKE_COLOR

class SpikyHouseplant(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int):
        super().__init__()
        self.radius = HOUSEPLANT_RADIUS
        self.collision_radius = HOUSEPLANT_COLLISION_RADIUS
        self.shadow_radius = max(1, int(self.collision_radius * 1.8))
        self.shadow_offset_scale = 1.0
        self.health = HOUSEPLANT_HEALTH
        self.max_health = HOUSEPLANT_HEALTH
        
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        # Main body
        pygame.draw.circle(
            self.image,
            HOUSEPLANT_BODY_COLOR,
            (self.radius, self.radius),
            self.radius - 2,
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
            pygame.draw.line(self.image, HOUSEPLANT_SPIKE_COLOR, start_p, end_p, 2)

        self.rect = self.image.get_rect(center=(x, y))
        self.x = float(x)
        self.y = float(y)

    def _take_damage(self, amount: int = 1) -> None:
        self.health -= amount
        if self.health <= 0:
            self.kill()
