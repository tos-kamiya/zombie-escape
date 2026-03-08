from __future__ import annotations

import pygame


class RectSprite(pygame.sprite.Sprite):
    """Sprite base class with non-optional ``image`` and ``rect`` fields."""

    image: pygame.Surface
    rect: pygame.Rect

