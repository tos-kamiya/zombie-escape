from __future__ import annotations

import math

import pygame

from ..colors import DARK_RED, ORANGE, YELLOW, EnvironmentPalette
from ..render_constants import ANGLE_BINS
from .common import ANGLE_STEP

_CAR_UPSCALE_FACTOR = 4

_CAR_COLOR_SCHEMES: dict[str, dict[str, tuple[int, int, int]]] = {
    "default": {
        "healthy": YELLOW,
        "damaged": ORANGE,
        "critical": DARK_RED,
    },
    "disabled": {
        "healthy": (185, 185, 185),
        "damaged": (150, 150, 150),
        "critical": (110, 110, 110),
    },
}


def resolve_car_color(
    *,
    health_ratio: float,
    appearance: str,
    palette: EnvironmentPalette | None = None,
) -> tuple[int, int, int]:
    _ = palette
    color_scheme = _CAR_COLOR_SCHEMES.get(appearance, _CAR_COLOR_SCHEMES["default"])
    color = color_scheme["healthy"]
    if health_ratio < 0.6:
        color = color_scheme["damaged"]
    if health_ratio < 0.3:
        color = color_scheme["critical"]
    return color


def build_car_surface(width: int, height: int) -> pygame.Surface:
    return pygame.Surface((width, height), pygame.SRCALPHA)


def paint_car_surface(
    surface: pygame.Surface,
    *,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    upscale = _CAR_UPSCALE_FACTOR
    if upscale > 1:
        up_width = width * upscale
        up_height = height * upscale
        up_surface = pygame.Surface((up_width, up_height), pygame.SRCALPHA)
        _paint_car_surface_base(
            up_surface, width=up_width, height=up_height, color=color
        )
        scaled = pygame.transform.smoothscale(up_surface, (width, height))
        surface.fill((0, 0, 0, 0))
        surface.blit(scaled, (0, 0))
        return
    _paint_car_surface_base(surface, width=width, height=height, color=color)


def _paint_car_surface_base(
    surface: pygame.Surface,
    *,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    surface.fill((0, 0, 0, 0))

    trim_color = tuple(int(c * 0.6) for c in color)
    body_color = tuple(min(255, int(c * 1.15)) for c in color)
    tail_light_color = (255, 80, 50)
    headlight_color = (200, 200, 200)

    base_width = 150.0
    base_height = 210.0
    scale_x = width / base_width
    scale_y = height / base_height

    def _rect(x: float, y: float, w: float, h: float) -> pygame.Rect:
        return pygame.Rect(
            int(round(x * scale_x)),
            int(round(y * scale_y)),
            max(1, int(round(w * scale_x))),
            max(1, int(round(h * scale_y))),
        )

    def _radius(value: float) -> int:
        return max(1, int(round(value * min(scale_x, scale_y))))

    body_top = _rect(0, 0, 150, 140)
    body_bottom = _rect(0, 70, 150, 140)
    rear_bed = _rect(16, 98, 118, 88)

    pygame.draw.rect(surface, trim_color, body_top, border_radius=_radius(50))
    pygame.draw.rect(surface, trim_color, body_bottom, border_radius=_radius(37))
    pygame.draw.rect(surface, body_color, rear_bed)

    tail_left = _rect(30, 190, 30, 20)
    tail_right = _rect(90, 190, 30, 20)
    pygame.draw.rect(surface, tail_light_color, tail_left)
    pygame.draw.rect(surface, tail_light_color, tail_right)

    headlight_left = _rect(15, 7, 40, 20)
    headlight_right = _rect(95, 7, 40, 20)
    pygame.draw.ellipse(surface, headlight_color, headlight_left)
    pygame.draw.ellipse(surface, headlight_color, headlight_right)


def build_car_directional_surfaces(
    base_surface: pygame.Surface, *, bins: int = ANGLE_BINS
) -> list[pygame.Surface]:
    surfaces: list[pygame.Surface] = []
    upscale = _CAR_UPSCALE_FACTOR
    if upscale > 1:
        src_size = base_surface.get_size()
        upscale_surface = pygame.transform.scale(
            base_surface,
            (src_size[0] * upscale, src_size[1] * upscale),
        )
    else:
        upscale_surface = base_surface
    for idx in range(bins):
        angle_rad = idx * ANGLE_STEP
        rotation_deg = -math.degrees(angle_rad) - 90
        rotated = pygame.transform.rotate(upscale_surface, rotation_deg)
        if upscale > 1:
            scaled = pygame.transform.smoothscale(
                rotated,
                (
                    max(1, rotated.get_width() // upscale),
                    max(1, rotated.get_height() // upscale),
                ),
            )
            surfaces.append(scaled)
        else:
            surfaces.append(rotated)
    return surfaces
