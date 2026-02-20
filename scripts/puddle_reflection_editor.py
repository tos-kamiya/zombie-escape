#!/usr/bin/env python3
"""Interactive editor for MOONLIGHT_REFLECTION_SPECS."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pygame

from zombie_escape.render.puddle import (
    MOONLIGHT_REFLECTION_SPECS,
    MoonlightReflectionSpec,
    draw_puddle_rings,
    get_puddle_wave_color,
)
from zombie_escape.render_constants import PUDDLE_TILE_COLOR

WINDOW_W = 1100
WINDOW_H = 760
FPS = 60
TILE_SIZE = 220
LOOP_FRAMES = 4
DEFAULT_CYCLE_MS = 900
EXPORT_PATH = Path("imgs/puddle-moonlight-loop/editor_export.json")


@dataclass
class Slider:
    label: str
    min_value: float
    max_value: float
    value: float
    rect: pygame.Rect
    decimals: int = 3
    dragging: bool = False

    def set_from_x(self, x: int) -> None:
        ratio = (x - self.rect.left) / max(1, self.rect.width)
        ratio = max(0.0, min(1.0, ratio))
        self.value = self.min_value + (self.max_value - self.min_value) * ratio

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.dragging = True
                self.set_from_x(event.pos[0])
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self.set_from_x(event.pos[0])
            return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, selected: bool) -> None:
        bg = (58, 66, 78) if selected else (44, 48, 56)
        pygame.draw.rect(surface, bg, self.rect, border_radius=6)
        ratio = (self.value - self.min_value) / max(1e-6, (self.max_value - self.min_value))
        fill_w = int(self.rect.width * max(0.0, min(1.0, ratio)))
        if fill_w > 0:
            pygame.draw.rect(
                surface,
                (120, 170, 220),
                pygame.Rect(self.rect.left, self.rect.top, fill_w, self.rect.height),
                border_radius=6,
            )
        pygame.draw.rect(surface, (150, 160, 180), self.rect, width=1, border_radius=6)
        text = f"{self.label}: {self.value:.{self.decimals}f}"
        surface.blit(font.render(text, True, (228, 232, 240)), (self.rect.left + 10, self.rect.top + 6))


def _specs_to_lists(specs: tuple[MoonlightReflectionSpec, ...]) -> list[list[float]]:
    return [list(spec) for spec in specs]


def _lists_to_specs(specs: list[list[float]]) -> tuple[MoonlightReflectionSpec, ...]:
    return tuple(tuple(float(v) for v in spec) for spec in specs)  # type: ignore[return-value]


def _draw_preview(
    surface: pygame.Surface,
    specs: list[list[float]],
    *,
    phase: int,
    top_left: tuple[int, int],
    alpha: int,
) -> None:
    tile = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
    tile_rect = tile.get_rect()
    pygame.draw.rect(tile, PUDDLE_TILE_COLOR, tile_rect)
    draw_puddle_rings(
        tile,
        rect=tile_rect,
        phase=phase,
        color=get_puddle_wave_color(alpha=alpha),
        width=3,
        reflection_specs=_lists_to_specs(specs),
    )
    surface.blit(tile, top_left)
    pygame.draw.rect(surface, (90, 102, 122), pygame.Rect(top_left, (TILE_SIZE, TILE_SIZE)), width=2)


def _draw_loop_strip(
    surface: pygame.Surface,
    specs: list[list[float]],
    *,
    top_left: tuple[int, int],
    alpha: int,
    active_phase: int,
) -> None:
    x0, y0 = top_left
    mini = 96
    pad = 10
    for phase in range(LOOP_FRAMES):
        tile = pygame.Surface((mini, mini), pygame.SRCALPHA)
        tile_rect = tile.get_rect()
        pygame.draw.rect(tile, PUDDLE_TILE_COLOR, tile_rect)
        draw_puddle_rings(
            tile,
            rect=tile_rect,
            phase=phase,
            color=get_puddle_wave_color(alpha=alpha),
            width=3,
            reflection_specs=_lists_to_specs(specs),
        )
        dst = (x0 + phase * (mini + pad), y0)
        surface.blit(tile, dst)
        border_color = (210, 220, 245) if phase == active_phase else (95, 105, 120)
        pygame.draw.rect(surface, border_color, pygame.Rect(dst, (mini, mini)), width=2)


def _export_specs(specs: list[list[float]], alpha: int, cycle_ms: int) -> None:
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "alpha": int(alpha),
        "cycle_ms": int(cycle_ms),
        "MOONLIGHT_REFLECTION_SPECS": [
            {
                "cx": round(s[0], 4),
                "cy": round(s[1], 4),
                "base_radius_ratio": round(s[2], 4),
                "pulse_ratio": round(s[3], 4),
                "phase_offset_radians": round(s[4], 4),
                "brightness_ratio": round(s[5], 4),
            }
            for s in specs
        ],
    }
    EXPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    pygame.init()
    pygame.display.set_caption("Puddle Moonlight Reflection Editor")
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 24)
    small = pygame.font.Font(None, 20)

    specs = _specs_to_lists(MOONLIGHT_REFLECTION_SPECS)
    selected = 0
    alpha = 210
    cycle_ms = DEFAULT_CYCLE_MS
    export_message = ""

    slider_defs = [
        ("cx", 0.0, 1.0, 3),
        ("cy", 0.0, 1.0, 3),
        ("radius", 0.05, 0.60, 3),
        ("pulse", 0.00, 0.18, 3),
        ("phase", 0.0, math.tau, 3),
        ("brightness", 0.20, 1.40, 3),
    ]

    sliders: list[Slider] = []
    sx = 560
    sy = 168
    sh = 34
    for idx, (label, lo, hi, dec) in enumerate(slider_defs):
        sliders.append(
            Slider(
                label=label,
                min_value=lo,
                max_value=hi,
                value=float(specs[selected][idx]),
                rect=pygame.Rect(sx, sy + idx * (sh + 10), 500, sh),
                decimals=dec,
            )
        )

    alpha_slider = Slider(
        label="alpha",
        min_value=40,
        max_value=255,
        value=float(alpha),
        rect=pygame.Rect(sx, sy + 6 * (sh + 10) + 20, 500, sh),
        decimals=0,
    )
    cycle_slider = Slider(
        label="cycle_ms",
        min_value=300,
        max_value=2200,
        value=float(cycle_ms),
        rect=pygame.Rect(sx, sy + 7 * (sh + 10) + 20, 500, sh),
        decimals=0,
    )

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    selected = int(event.unicode) - 1
                    for i, slider in enumerate(sliders):
                        slider.value = float(specs[selected][i])
                if event.key == pygame.K_s:
                    _export_specs(specs, int(alpha), int(cycle_ms))
                    export_message = f"exported: {EXPORT_PATH}"

            changed = False
            for i, slider in enumerate(sliders):
                if slider.handle_event(event):
                    specs[selected][i] = slider.value
                    changed = True
            if alpha_slider.handle_event(event):
                alpha = int(alpha_slider.value)
                changed = True
            if cycle_slider.handle_event(event):
                cycle_ms = int(cycle_slider.value)
                changed = True
            if changed:
                export_message = ""

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for idx in range(4):
                    tab_rect = pygame.Rect(560 + idx * 126, 110, 116, 42)
                    if tab_rect.collidepoint(mx, my):
                        selected = idx
                        for i, slider in enumerate(sliders):
                            slider.value = float(specs[selected][i])

        elapsed = pygame.time.get_ticks()
        phase = (elapsed // max(1, cycle_ms)) % LOOP_FRAMES

        screen.fill((24, 28, 36))
        screen.blit(font.render("Puddle Reflection Editor", True, (230, 236, 246)), (24, 18))
        screen.blit(
            small.render("Drag sliders, press 1-4 to switch circle, press S to export.", True, (180, 188, 202)),
            (24, 48),
        )

        _draw_preview(screen, specs, phase=int(phase), top_left=(24, 86), alpha=int(alpha))
        _draw_loop_strip(screen, specs, top_left=(24, 336), alpha=int(alpha), active_phase=int(phase))

        for idx in range(4):
            tab = pygame.Rect(560 + idx * 126, 110, 116, 42)
            tab_color = (102, 140, 188) if idx == selected else (56, 62, 74)
            pygame.draw.rect(screen, tab_color, tab, border_radius=8)
            pygame.draw.rect(screen, (150, 160, 182), tab, width=1, border_radius=8)
            screen.blit(font.render(f"Circle {idx + 1}", True, (230, 236, 246)), (tab.left + 12, tab.top + 10))

        for slider in sliders:
            slider.draw(screen, small, True)
        alpha_slider.draw(screen, small, True)
        cycle_slider.draw(screen, small, True)

        y = 560
        for idx, spec in enumerate(specs):
            line = (
                f"{idx + 1}: ({spec[0]:.3f}, {spec[1]:.3f}, {spec[2]:.3f}, "
                f"{spec[3]:.3f}, {spec[4]:.3f}, {spec[5]:.3f})"
            )
            screen.blit(small.render(line, True, (198, 206, 220)), (24, y))
            y += 26

        if export_message:
            screen.blit(small.render(export_message, True, (206, 236, 190)), (24, 700))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
