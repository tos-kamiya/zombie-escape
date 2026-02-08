from __future__ import annotations

import numpy as np  # type: ignore
import pygame


def build_grayscale_image(source: pygame.Surface) -> pygame.Surface:
    image = source.copy()
    image = image.convert_alpha()
    rgb = pygame.surfarray.pixels3d(image)
    alpha = pygame.surfarray.pixels_alpha(image)
    gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]).astype(
        np.uint8
    )
    rgb[:, :, 0] = gray
    rgb[:, :, 1] = gray
    rgb[:, :, 2] = gray
    del rgb, alpha
    return image
