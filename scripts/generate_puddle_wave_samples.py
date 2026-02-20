#!/usr/bin/env python3
"""Generate puddle-wave sample images and matching parameter sets."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import pygame

from zombie_escape.render_constants import PUDDLE_TILE_COLOR
from zombie_escape.render.puddle import draw_puddle_rings, get_puddle_wave_color
import zombie_escape.render.puddle as puddle_module


def _random_ripple_specs(rng: random.Random) -> list[tuple[float, float, float, float, int]]:
    specs: list[tuple[float, float, float, float, int]] = []
    for _ in range(4):
        cx = rng.uniform(0.28, 0.72)
        cy = rng.uniform(0.28, 0.72)
        w_ratio = rng.uniform(0.55, 1.20)
        h_ratio = rng.uniform(0.45, 1.05)
        # Smaller ellipse gets thicker line.
        area_like = w_ratio * h_ratio
        if area_like < 0.42:
            thickness = rng.randint(5, 6)
        elif area_like < 0.62:
            thickness = rng.randint(4, 5)
        else:
            thickness = rng.randint(3, 4)
        specs.append((cx, cy, w_ratio, h_ratio, thickness))
    return specs


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _load_reference_specs(path: Path) -> list[tuple[float, float, float, float, int]]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    specs_payload = payload.get("ripple_specs")
    if not isinstance(specs_payload, list) or not specs_payload:
        raise ValueError(f"Invalid ripple_specs in {path}")
    specs: list[tuple[float, float, float, float, int]] = []
    for item in specs_payload:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid ripple spec item in {path}")
        specs.append(
            (
                float(item["cx_ratio"]),
                float(item["cy_ratio"]),
                float(item["w_ratio"]),
                float(item["h_ratio"]),
                int(item["line_width"]),
            )
        )
    return specs


def _jittered_specs_from_reference(
    rng: random.Random,
    *,
    reference_specs: list[tuple[float, float, float, float, int]],
    pos_jitter: float,
    size_jitter: float,
    circle_bias: float,
) -> list[tuple[float, float, float, float, int]]:
    specs: list[tuple[float, float, float, float, int]] = []
    for (cx, cy, wr, hr, _) in reference_specs:
        jcx = _clamp(cx + rng.uniform(-pos_jitter, pos_jitter), 0.18, 0.82)
        jcy = _clamp(cy + rng.uniform(-pos_jitter, pos_jitter), 0.18, 0.82)
        jwr = _clamp(wr + rng.uniform(-size_jitter, size_jitter), 0.40, 1.35)
        jhr = _clamp(hr + rng.uniform(-size_jitter, size_jitter), 0.35, 1.20)
        # Pull ellipse shape toward a circle while preserving overall size feel.
        circle_size = (jwr + jhr) * 0.5
        jwr = _clamp(jwr * (1.0 - circle_bias) + circle_size * circle_bias, 0.40, 1.35)
        jhr = _clamp(jhr * (1.0 - circle_bias) + circle_size * circle_bias, 0.35, 1.20)
        # Smaller ellipse gets thicker line.
        area_like = jwr * jhr
        if area_like < 0.42:
            thickness = rng.randint(5, 6)
        elif area_like < 0.62:
            thickness = rng.randint(4, 5)
        else:
            thickness = rng.randint(3, 4)
        specs.append((jcx, jcy, jwr, jhr, thickness))
    return specs


def _save_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_samples(
    *,
    out_dir: Path,
    count: int,
    cell_size: int,
    seed: int | None,
    reference_json: Path | None,
    phase_jitter: int,
    pos_jitter: float,
    size_jitter: float,
    circle_bias: float,
) -> None:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    reference_specs = (
        _load_reference_specs(reference_json) if reference_json is not None else None
    )
    reference_phase: int | None = None
    if reference_json is not None:
        payload: dict[str, Any] = json.loads(reference_json.read_text(encoding="utf-8"))
        raw_phase = payload.get("phase")
        if isinstance(raw_phase, int):
            reference_phase = raw_phase

    manifest: list[dict] = []
    base_color = tuple(int(c) for c in PUDDLE_TILE_COLOR)
    wave_color = get_puddle_wave_color(alpha=180)

    for idx in range(count):
        if reference_specs is None:
            specs = _random_ripple_specs(rng)
            phase = rng.randint(0, 15)
        else:
            specs = _jittered_specs_from_reference(
                rng,
                reference_specs=reference_specs,
                pos_jitter=pos_jitter,
                size_jitter=size_jitter,
                circle_bias=circle_bias,
            )
            if reference_phase is None:
                phase = rng.randint(0, 15)
            else:
                phase = int(_clamp(
                    reference_phase + rng.randint(-phase_jitter, phase_jitter),
                    0,
                    15,
                ))

        # The user-edited draw_puddle_rings currently reads global `ripple_specs`.
        # Keep the script compatible by injecting per-sample specs when available.
        if hasattr(puddle_module, "ripple_specs"):
            puddle_module.ripple_specs = specs  # type: ignore[attr-defined]

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

        stem = f"puddle_wave_{idx:03d}"
        image_path = out_dir / f"{stem}.png"
        params_path = out_dir / f"{stem}.json"
        pygame.image.save(tile, str(image_path))

        params = {
            "index": idx,
            "phase": phase,
            "cell_size": cell_size,
            "base_color": list(base_color),
            "wave_color": list(wave_color) if isinstance(wave_color, tuple) else wave_color,
            "ripple_specs": [
                {
                    "cx_ratio": round(cx, 4),
                    "cy_ratio": round(cy, 4),
                    "w_ratio": round(wr, 4),
                    "h_ratio": round(hr, 4),
                    "line_width": int(t),
                }
                for (cx, cy, wr, hr, t) in specs
            ],
            "image": image_path.name,
        }
        _save_json(params_path, params)
        manifest.append(params)

    _save_json(
        out_dir / "manifest.json",
        {
            "count": count,
            "cell_size": cell_size,
            "seed": seed,
            "items": manifest,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate puddle-wave sample PNGs and parameter JSON sets."
    )
    parser.add_argument(
        "--out-dir",
        default="imgs/puddle-wave-samples",
        help="Output directory (default: imgs/puddle-wave-samples)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of samples to generate (default: 100)",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=50,
        help="Tile size in pixels (default: 50)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--reference-json",
        default=None,
        help="Reference sample JSON path (e.g. puddle_wave_041.json)",
    )
    parser.add_argument(
        "--phase-jitter",
        type=int,
        default=2,
        help="Max +/- jitter for phase when reference JSON is used (default: 2)",
    )
    parser.add_argument(
        "--pos-jitter",
        type=float,
        default=0.08,
        help="Max +/- jitter for cx/cy when reference JSON is used (default: 0.08)",
    )
    parser.add_argument(
        "--size-jitter",
        type=float,
        default=0.12,
        help="Max +/- jitter for w/h when reference JSON is used (default: 0.12)",
    )
    parser.add_argument(
        "--circle-bias",
        type=float,
        default=0.35,
        help=(
            "How much to pull w/h toward a circle (0.0-1.0) "
            "when reference JSON is used (default: 0.35)"
        ),
    )
    args = parser.parse_args()

    generate_samples(
        out_dir=Path(args.out_dir),
        count=max(1, args.count),
        cell_size=max(8, args.cell_size),
        seed=args.seed,
        reference_json=Path(args.reference_json) if args.reference_json else None,
        phase_jitter=max(0, args.phase_jitter),
        pos_jitter=max(0.0, args.pos_jitter),
        size_jitter=max(0.0, args.size_jitter),
        circle_bias=_clamp(float(args.circle_bias), 0.0, 1.0),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
