from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import MATERIAL_SIZE

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .carrier_bot import CarrierBot


class Material(pygame.sprite.Sprite):
    """Passive carryable object for carrier bots."""

    def __init__(self: Self, x: float, y: float, *, size: int = MATERIAL_SIZE) -> None:
        super().__init__()
        safe_size = max(4, int(size))
        self.image = pygame.Surface((safe_size, safe_size), pygame.SRCALPHA)
        self.image.fill((182, 152, 108))
        pygame.draw.rect(self.image, (70, 56, 30), self.image.get_rect(), width=1)
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.collision_radius = float(max(1.0, safe_size * 0.5))
        self.carried_by: CarrierBot | None = None

    def place_at(self: Self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.rect.center = (int(self.x), int(self.y))
