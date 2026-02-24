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
        body_color = (72, 132, 168)
        frame_color = (34, 82, 108)
        wire_color = (92, 98, 110)
        inset = max(1, safe_size // 10)
        jag = max(1, safe_size // 40)
        left = inset
        right = safe_size - 1 - inset
        top = inset
        bottom = safe_size - 1 - inset
        mid1 = max(left + 1, min(right - 1, safe_size // 3))
        mid2 = max(left + 1, min(right - 1, (safe_size * 2) // 3))
        cloth_outline = [
            (left + jag, top),
            (mid1, top + jag),
            (mid2, top),
            (right - jag, top + jag),
            (right, mid1),
            (right - jag, mid2),
            (right, bottom - jag),
            (mid2, bottom),
            (mid1, bottom - jag),
            (left + jag, bottom),
            (left, mid2),
            (left + jag, mid1),
        ]
        pygame.draw.polygon(self.image, body_color, cloth_outline)
        pygame.draw.polygon(self.image, frame_color, cloth_outline, width=1)
        # Two vertical and two horizontal wire bands.
        wire_width = max(1, safe_size // 10)
        x_positions = (safe_size // 3, (safe_size * 2) // 3)
        y_positions = (safe_size // 3, (safe_size * 2) // 3)
        for x_pos in x_positions:
            pygame.draw.line(
                self.image,
                wire_color,
                (x_pos, top + 1),
                (x_pos, bottom - 1),
                width=wire_width,
            )
        for y_pos in y_positions:
            pygame.draw.line(
                self.image,
                wire_color,
                (left + 1, y_pos),
                (right - 1, y_pos),
                width=wire_width,
            )
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.collision_radius = float(max(1.0, safe_size * 0.5))
        self.carried_by: CarrierBot | None = None

    def place_at(self: Self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.rect.center = (int(self.x), int(self.y))
