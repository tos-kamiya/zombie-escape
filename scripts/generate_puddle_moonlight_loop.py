#!/usr/bin/env python3
"""Generate 4-loop-frame moonlight puddle reflection samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pygame

from zombie_escape.render.puddle import (
    MOONLIGHT_REFLECTION_SPECS,
    draw_puddle_rings,
    get_puddle_wave_color,
)
from zombie_escape.render_constants import PUDDLE_TILE_COLOR


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_loop(*, out_dir: Path, cell_size: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    base_color = tuple(int(c) for c in PUDDLE_TILE_COLOR)
    wave_color = get_puddle_wave_color(alpha=210)
    frames: list[dict[str, Any]] = []

    for phase in range(4):
        tile = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
        tile_rect = tile.get_rect()
        pygame.draw.rect(tile, base_color, tile_rect)
        draw_puddle_rings(
            tile,
            rect=tile_rect,
            phase=phase,
            color=wave_color,
            width=3,
        )

        image_name = f"puddle_moonlight_loop_{phase:02d}.png"
        image_path = out_dir / image_name
        pygame.image.save(tile, str(image_path))

        frames.append(
            {
                "phase": phase,
                "image": image_name,
            }
        )

    _save_json(
        out_dir / "manifest.json",
        {
            "loop_frames": 4,
            "cell_size": cell_size,
            "base_color": list(base_color),
            "wave_color": list(wave_color) if isinstance(wave_color, tuple) else wave_color,
            "moonlight_reflection_specs": [
                {
                    "cx_ratio": cx,
                    "cy_ratio": cy,
                    "base_radius_ratio": radius_ratio,
                    "pulse_ratio": pulse_ratio,
                    "phase_offset_radians": phase_offset,
                    "brightness_ratio": brightness_ratio,
                }
                for (
                    cx,
                    cy,
                    radius_ratio,
                    pulse_ratio,
                    phase_offset,
                    brightness_ratio,
                ) in MOONLIGHT_REFLECTION_SPECS
            ],
            "frames": frames,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate moonlight puddle loop frames (4 PNGs + manifest)."
    )
    parser.add_argument(
        "--out-dir",
        default="imgs/puddle-moonlight-loop",
        help="Output directory (default: imgs/puddle-moonlight-loop)",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=50,
        help="Tile size in pixels (default: 50)",
    )
    args = parser.parse_args()

    generate_loop(
        out_dir=Path(args.out_dir),
        cell_size=max(8, args.cell_size),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
