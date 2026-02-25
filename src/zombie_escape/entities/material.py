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
        body_color = (56, 60, 66)
        frame_color = (24, 27, 32)
        wire_color = (104, 110, 120)
        inset = max(1, safe_size // 10)
        left = inset
        right = safe_size - 1 - inset
        top = inset
        bottom = safe_size - 1 - inset
        body_rect = pygame.Rect(left, top, right - left + 1, bottom - top + 1)
        # Draw as stacked metal plates: top face + visible front cross-section.
        front_depth = max(2, body_rect.height // 5)
        top_rect = pygame.Rect(
            body_rect.left,
            body_rect.top,
            body_rect.width,
            max(1, body_rect.height - front_depth),
        )
        front_rect = pygame.Rect(
            body_rect.left,
            top_rect.bottom,
            body_rect.width,
            max(1, body_rect.bottom - top_rect.bottom + 1),
        )
        pygame.draw.rect(self.image, body_color, top_rect)
        pygame.draw.rect(self.image, frame_color, top_rect, width=1)

        front_base_color = (46, 49, 55)
        pygame.draw.rect(self.image, front_base_color, front_rect)
        pygame.draw.rect(self.image, frame_color, front_rect, width=1)
        plate_line_colors = ((70, 74, 82), (58, 62, 70))
        plate_lines = max(2, min(4, front_rect.height))
        for i in range(1, plate_lines):
            y_pos = front_rect.top + (i * front_rect.height) // plate_lines
            pygame.draw.line(
                self.image,
                plate_line_colors[i % 2],
                (front_rect.left + 1, y_pos),
                (front_rect.right - 1, y_pos),
                width=1,
            )

        pygame.draw.rect(self.image, frame_color, body_rect, width=1)
        # Two vertical and two horizontal wire bands.
        # Vertical bands continue across the front cross-section.
        wire_width = max(1, safe_size // 10)
        x_positions = (safe_size // 3, (safe_size * 2) // 3)
        y_positions = (
            top_rect.top + max(1, top_rect.height // 3),
            top_rect.top + max(1, (top_rect.height * 2) // 3),
        )
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
        # Entity-shadow system uses radius; 0.8x icon width => 0.4x radius.
        self.shadow_radius = max(1, int(safe_size * 0.4))
        self.shadow_shape = "rect"
        self.shadow_size = (
            max(1, int(safe_size * 1.2)),
            max(1, int(safe_size * 1.2)),
        )
        self.shadow_offset_scale = 1.0
        self.carried_by: CarrierBot | None = None

    def place_at(self: Self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.rect.center = (int(self.x), int(self.y))
