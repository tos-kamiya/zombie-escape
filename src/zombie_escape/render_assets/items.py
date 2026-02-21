from __future__ import annotations

from dataclasses import dataclass

import pygame

from ..colors import BLACK, LIGHT_GRAY, YELLOW


@dataclass(frozen=True)
class PolygonSpec:
    size: tuple[int, int]
    polygons: list[list[tuple[int, int]]]


FLASHLIGHT_SPEC = PolygonSpec(
    size=(12, 10),
    polygons=[
        [
            (1, 2),
            (8, 2),
            (8, 7),
            (1, 7),
        ],
        [
            (8, 1),
            (11, 1),
            (11, 8),
            (8, 8),
        ],
    ],
)

SHOES_SPEC = PolygonSpec(
    size=(14, 10),
    polygons=[
        [
            (1, 1),
            (7, 1),
            (8, 4),
            (13, 6),
            (13, 9),
            (1, 9),
        ],
    ],
)


def _scale_polygons(
    spec: PolygonSpec,
    dst_size: tuple[int, int],
) -> list[list[tuple[int, int]]]:
    src_w, src_h = spec.size
    dst_w, dst_h = dst_size
    scale_x = dst_w / max(1, src_w)
    scale_y = dst_h / max(1, src_h)
    scaled = []
    for poly in spec.polygons:
        scaled.append(
            [
                (
                    int(round(x * scale_x)),
                    int(round(y * scale_y)),
                )
                for x, y in poly
            ]
        )
    return scaled


def _draw_polygon_surface(
    width: int,
    height: int,
    spec: PolygonSpec,
    *,
    fill_color: tuple[int, int, int] = YELLOW,
    outline_color: tuple[int, int, int] = BLACK,
) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    draw_polygons = spec.polygons
    if (width, height) != spec.size:
        draw_polygons = _scale_polygons(spec, (width, height))
    for poly in draw_polygons:
        pygame.draw.polygon(surface, fill_color, poly)
        pygame.draw.polygon(surface, outline_color, poly, width=1)
    return surface


def _draw_fuel_can_body(
    surface: pygame.Surface,
    width: int,
    height: int,
    *,
    fill_color: tuple[int, int, int],
    emboss_color: tuple[int, int, int] | None = None,
) -> None:
    x1 = max(1, int(round(width * 0.10)))
    y1 = max(1, int(round(height * 0.10)))
    x2 = min(width - 2, int(round(width * 0.78)))
    y2 = max(y1 + 1, int(round(height * 0.14)))
    x3 = min(width - 2, int(round(width * 0.86)))
    y3 = min(height - 2, int(round(height * 0.23)))
    x4 = x3
    y4 = min(height - 2, int(round(height * 0.92)))
    x5 = x1
    y5 = y4
    body_points = [
        (x1, y1),
        (x2, y2),
        (x3, y3),
        (x4, y4),
        (x5, y5),
    ]
    pygame.draw.polygon(surface, fill_color, body_points)
    pygame.draw.polygon(surface, BLACK, body_points, width=1)
    x_left = x1 + max(2, int(round((x3 - x1) * 0.22)))
    x_right = x3 - max(2, int(round((x3 - x1) * 0.22)))
    y_top = y1 + max(3, int(round((y4 - y1) * 0.24)))
    y_bottom = y4 - max(3, int(round((y4 - y1) * 0.20)))
    if x_right > x_left and y_bottom > y_top:
        highlight = emboss_color or tuple(min(255, c + 36) for c in fill_color)
        pygame.draw.line(
            surface, highlight, (x_left, y_top), (x_right, y_bottom), width=1
        )
        pygame.draw.line(
            surface, highlight, (x_left, y_bottom), (x_right, y_top), width=1
        )


def _draw_fuel_can_cap(
    surface: pygame.Surface,
    width: int,
    height: int,
    *,
    fill_color: tuple[int, int, int],
) -> None:
    cap = pygame.Rect(
        max(0, int(round(width * 0.66))),
        max(0, int(round(height * 0.06))),
        max(3, int(round(width * 0.30))),
        max(2, int(round(height * 0.22))),
    )
    cap.clamp_ip(surface.get_rect())
    pygame.draw.rect(surface, fill_color, cap, border_radius=1)
    pygame.draw.rect(surface, BLACK, cap, width=1, border_radius=1)


def build_fuel_can_surface(width: int, height: int) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    _draw_fuel_can_body(
        surface,
        width,
        height,
        fill_color=YELLOW,
        emboss_color=(185, 155, 20),
    )
    _draw_fuel_can_cap(surface, width, height, fill_color=BLACK)
    return surface


def build_empty_fuel_can_surface(width: int, height: int) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    _draw_fuel_can_body(surface, width, height, fill_color=LIGHT_GRAY)
    _draw_fuel_can_cap(surface, width, height, fill_color=YELLOW)
    return surface


def build_fuel_station_surface(width: int, height: int) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)

    def sx(px: int) -> int:
        return int(round(px * width / 14))

    def sy(py: int) -> int:
        return int(round(py * height / 18))

    base = pygame.Rect(sx(0), sy(15), max(1, sx(9) - sx(0)), max(1, sy(18) - sy(15)))
    pygame.draw.rect(surface, YELLOW, base)
    pygame.draw.rect(surface, BLACK, base, width=1)

    body = pygame.Rect(sx(1), sy(1), max(1, sx(8) - sx(1)), max(1, sy(16) - sy(1)))
    pygame.draw.rect(surface, YELLOW, body)
    pygame.draw.rect(surface, BLACK, body, width=1)

    panel = pygame.Rect(sx(2), sy(3), max(1, sx(7) - sx(2)), max(1, sy(7) - sy(3)))
    pygame.draw.rect(surface, BLACK, panel)

    arm = pygame.Rect(sx(9), sy(4), max(1, sx(10) - sx(9)), max(1, sy(5) - sy(4)))
    pygame.draw.rect(surface, BLACK, arm)

    nozzle = pygame.Rect(sx(10), sy(4), max(1, sx(13) - sx(10)), max(1, sy(7) - sy(4)))
    pygame.draw.rect(surface, YELLOW, nozzle)
    pygame.draw.rect(surface, BLACK, nozzle, width=1)

    hose_w = max(1, sx(11) - sx(10))
    hose_h = max(2, sy(14) - sy(7))
    hose = pygame.Rect(sx(10), sy(7), hose_w, hose_h)
    pygame.draw.rect(surface, BLACK, hose, width=1)

    tip = pygame.Rect(sx(9), sy(13), max(1, sx(10) - sx(9)), max(1, sy(14) - sy(13)))
    pygame.draw.rect(surface, BLACK, tip)

    lower_hose = pygame.Rect(
        sx(9),
        sy(14),
        max(1, sx(10) - sx(9)),
        max(1, sy(16) - sy(14)),
    )
    pygame.draw.rect(surface, BLACK, lower_hose)
    body_connector = pygame.Rect(
        sx(8),
        sy(15),
        max(1, sx(9) - sx(8)),
        max(1, sy(16) - sy(15)),
    )
    pygame.draw.rect(surface, BLACK, body_connector)

    return surface


def build_flashlight_surface(width: int, height: int) -> pygame.Surface:
    return _draw_polygon_surface(width, height, FLASHLIGHT_SPEC)


def build_shoes_surface(width: int, height: int) -> pygame.Surface:
    return _draw_polygon_surface(width, height, SHOES_SPEC)
