from __future__ import annotations

import argparse
import sys
import traceback  # For error reporting
from pathlib import Path
from typing import Any, Tuple

import pygame

try:
    from .__about__ import __version__
except Exception:  # pragma: no cover - fallback version
    __version__ = "0.0.0-unknown"
from .config import load_config, save_config
from .entities_constants import (
    CAR_SPEED,
    SURVIVOR_MAX_SAFE_PASSENGERS,
    SURVIVOR_MIN_SPEED_FACTOR,
)
from .gameplay import calculate_car_speed_for_passengers
from .level_constants import DEFAULT_TILE_SIZE
from .localization import set_language
from .models import GameData, Stage
from .render_constants import RenderAssets, build_render_assets
from .screen_constants import (
    DEFAULT_WINDOW_SCALE,
    FPS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from .screens import ScreenID, ScreenTransition, apply_window_scale
from .screens.game_over import game_over_screen
from .screens.settings import settings_screen
from .screens.title import MAX_SEED_DIGITS, title_screen
from .stage_constants import DEFAULT_STAGE_ID, STAGES


def _parse_cli_args(argv: list[str]) -> Tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debugging aids for Stage 5 and hide pause overlay",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Profile gameplay and write cProfile output to disk",
    )
    parser.add_argument(
        "--profile-output",
        default="profile.prof",
        help="cProfile output path (default: profile.prof)",
    )
    parser.add_argument("--seed")
    return parser.parse_known_args(argv)


def _sanitize_seed_text(raw: str | None) -> tuple[str | None, bool]:
    if not raw:
        return None, True
    stripped = raw.strip()
    if not stripped.isdigit():
        print("Ignoring --seed value because it must contain only digits.")
        return None, True
    return stripped[:MAX_SEED_DIGITS], False


# Re-export the gameplay helpers constants for external callers/tests.
__all__ = [
    "main",
    "CAR_SPEED",
    "SURVIVOR_MAX_SAFE_PASSENGERS",
    "SURVIVOR_MIN_SPEED_FACTOR",
    "calculate_car_speed_for_passengers",
]


# --- Main Entry Point ---
def main() -> None:
    args, remaining = _parse_cli_args(sys.argv[1:])
    sys.argv = [sys.argv[0]] + remaining

    pygame.init()
    pygame.joystick.init()
    if hasattr(pygame, "controller"):
        pygame.controller.init()
    try:
        pygame.font.init()
    except pygame.error as e:
        print(f"Pygame font failed to initialize: {e}")
        # Font errors are often non-fatal, continue without fonts or handle gracefully

    from .screens.gameplay import gameplay_screen

    apply_window_scale(DEFAULT_WINDOW_SCALE)
    pygame.mouse.set_visible(True)
    screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert_alpha()
    clock = pygame.time.Clock()

    debug_mode = bool(args.debug)
    cli_seed_text, cli_seed_is_auto = _sanitize_seed_text(args.seed)
    title_seed_text, title_seed_is_auto = cli_seed_text, cli_seed_is_auto
    last_stage_id: str | None = None

    config: dict[str, Any]
    config, config_path = load_config()
    if not config_path.exists():
        save_config(config, config_path)
    set_language(config.get("language"))

    def _profiled_gameplay_screen(
        screen: pygame.Surface,
        clock: pygame.time.Clock,
        config: dict[str, Any],
        fps: int,
        stage: Stage,
        *,
        show_pause_overlay: bool,
        seed: int | None,
        render_assets: RenderAssets,
        debug_mode: bool,
    ) -> ScreenTransition:
        import cProfile
        import pstats

        profiler = cProfile.Profile()
        try:
            return profiler.runcall(
                gameplay_screen,
                screen,
                clock,
                config,
                fps,
                stage,
                show_pause_overlay=show_pause_overlay,
                seed=seed,
                render_assets=render_assets,
                debug_mode=debug_mode,
            )
        finally:
            output_path = Path(args.profile_output)
            profiler.dump_stats(output_path)
            summary_path = output_path.with_suffix(".txt")
            with summary_path.open("w", encoding="utf-8") as handle:
                stats = pstats.Stats(
                    profiler,
                    stream=handle,
                ).sort_stats("tottime")
                stats.print_stats(50)
            print(f"Profile saved to {output_path} and {summary_path}")

    next_screen = ScreenID.TITLE
    transition: ScreenTransition | None = None
    running = True

    while running:
        incoming = transition
        transition = None

        if next_screen == ScreenID.TITLE:
            seed_input = None if title_seed_is_auto else title_seed_text
            transition = title_screen(
                screen,
                clock,
                config,
                FPS,
                stages=STAGES,
                default_stage_id=last_stage_id or DEFAULT_STAGE_ID,
                screen_size=(SCREEN_WIDTH, SCREEN_HEIGHT),
                seed_text=seed_input,
                seed_is_auto=title_seed_is_auto,
            )
            if transition.seed_text is not None:
                title_seed_text = transition.seed_text
                title_seed_is_auto = transition.seed_is_auto
        elif next_screen == ScreenID.SETTINGS:
            config = settings_screen(
                screen,
                clock,
                config,
                FPS,
                config_path=config_path,
                screen_size=(SCREEN_WIDTH, SCREEN_HEIGHT),
            )
            set_language(config.get("language"))
            transition = ScreenTransition(ScreenID.TITLE)
        elif next_screen == ScreenID.GAMEPLAY:
            stage = incoming.stage
            seed_value = incoming.seed
            if stage is None:
                transition = ScreenTransition(ScreenID.TITLE)
            else:
                last_stage_id = stage.id
                render_assets = build_render_assets(stage.tile_size)
                try:
                    gs = _profiled_gameplay_screen if args.profile else gameplay_screen
                    transition = gs(
                        screen,
                        clock,
                        config,
                        FPS,
                        stage,
                        show_pause_overlay=not debug_mode,
                        seed=seed_value,
                        render_assets=render_assets,
                        debug_mode=debug_mode,
                    )
                except SystemExit:
                    running = False
                    break
                except Exception:
                    print("An unhandled error occurred during game execution:")
                    traceback.print_exc()
                    running = False
                    break
        elif next_screen == ScreenID.GAME_OVER:
            game_data = incoming.game_data if incoming else None
            stage = incoming.stage if incoming else None
            config_payload = incoming.config if incoming else None
            assert config_payload is not None
            if game_data is not None:
                render_assets = build_render_assets(game_data.cell_size)
            elif stage is not None:
                render_assets = build_render_assets(stage.tile_size)
            else:
                render_assets = build_render_assets(DEFAULT_TILE_SIZE)
            transition = game_over_screen(
                screen,
                clock,
                config_payload,
                FPS,
                game_data=game_data,
                stage=stage,
                render_assets=render_assets,
            )
        elif next_screen == ScreenID.EXIT:
            break
        else:
            transition = ScreenTransition(ScreenID.TITLE)

        if not transition:
            break

        if transition.next_screen == ScreenID.GAMEPLAY:
            title_seed_text = cli_seed_text
            title_seed_is_auto = cli_seed_is_auto
        next_screen = transition.next_screen

    pygame.quit()  # Quit pygame only once at the very end of main
    sys.exit()  # Exit the script


if __name__ == "__main__":
    main()
