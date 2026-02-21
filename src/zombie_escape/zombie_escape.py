from __future__ import annotations

import argparse
import logging
import os
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
from .level_constants import DEFAULT_CELL_SIZE
from .localization import set_language
from .models import Stage
from .render_constants import RenderAssets, build_render_assets
from .screen_constants import (
    DEFAULT_WINDOW_SCALE,
    FPS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from .screens import ScreenID, ScreenTransition
from .windowing import (
    adjust_menu_logical_size,
    apply_window_scale,
    prime_scaled_logical_size,
    set_scaled_logical_size,
)
from .screens.game_over import game_over_screen
from .screens.settings import settings_screen
from .screens.startup_check import startup_check_screen
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
        "--show-fps",
        action="store_true",
        help="Show FPS overlay during gameplay",
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
    parser.add_argument(
        "--export-images",
        action="store_true",
        help="Export documentation images to imgs/exports at 4x size and exit",
    )
    parser.add_argument(
        "--build-fog-cache",
        action="store_true",
        dest="build_fog_cache",
        help="Precompute and save fog cache files for all darkness profiles, then exit",
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

    log_level = os.environ.get("ZOMBIE_ESCAPE_LOG_LEVEL")
    if log_level:
        logging.basicConfig(
            level=log_level.upper(),
            format="%(levelname)s %(name)s: %(message)s",
        )

    os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "0")
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

    prime_scaled_logical_size((SCREEN_WIDTH, SCREEN_HEIGHT))
    apply_window_scale(DEFAULT_WINDOW_SCALE)
    pygame.mouse.set_visible(True)
    logical_screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert_alpha()
    menu_screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert_alpha()
    clock = pygame.time.Clock()

    debug_mode = bool(args.debug)
    show_fps = bool(args.show_fps) or debug_mode
    cli_seed_text, cli_seed_is_auto = _sanitize_seed_text(args.seed)
    title_seed_text, title_seed_is_auto = cli_seed_text, cli_seed_is_auto
    last_stage_id: str | None = None

    if args.export_images:
        from .export_images import export_images

        output_dir = Path.cwd() / "imgs" / "exports"
        saved = export_images(output_dir, cell_size=DEFAULT_CELL_SIZE)
        print(f"Exported {len(saved)} images to {output_dir}")
        pygame.quit()
        return
    if args.build_fog_cache:
        from .render.fog import save_all_fog_caches

        output_dir = Path(__file__).resolve().parent / "assets" / "fog_cache"
        assets = build_render_assets(DEFAULT_CELL_SIZE)
        saved_paths = save_all_fog_caches(assets, output_dir=output_dir)
        for path in saved_paths:
            print(f"Saved fog cache: {path}")
        pygame.quit()
        return

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
        show_fps: bool,
    ) -> ScreenTransition:
        import cProfile

        profiler = cProfile.Profile()
        output_path = Path(args.profile_output)
        print("Profile ready. Press F10 in gameplay to start/stop and save.")
        return gameplay_screen(
            screen,
            clock,
            config,
            fps,
            stage,
            show_pause_overlay=show_pause_overlay,
            seed=seed,
            render_assets=render_assets,
            debug_mode=debug_mode,
            show_fps=show_fps,
            profiler=profiler,
            profiler_output=output_path,
        )

    next_screen = ScreenID.STARTUP_CHECK
    transition: ScreenTransition | None = None
    running = True

    while running:
        incoming = transition
        transition = None

        if next_screen == ScreenID.STARTUP_CHECK:
            adjust_menu_logical_size()
            transition = startup_check_screen(
                menu_screen,
                clock,
                config,
                FPS,
                screen_size=menu_screen.get_size(),
            )
        elif next_screen == ScreenID.TITLE:
            adjust_menu_logical_size()
            seed_input = None if title_seed_is_auto else title_seed_text
            transition = title_screen(
                menu_screen,
                clock,
                config,
                FPS,
                stages=STAGES,
                default_stage_id=last_stage_id or DEFAULT_STAGE_ID,
                screen_size=menu_screen.get_size(),
                seed_text=seed_input,
                seed_is_auto=title_seed_is_auto,
            )
            if transition.seed_text is not None:
                title_seed_text = transition.seed_text
                title_seed_is_auto = transition.seed_is_auto
        elif next_screen == ScreenID.SETTINGS:
            adjust_menu_logical_size()
            config = settings_screen(
                menu_screen,
                clock,
                config,
                FPS,
                config_path=config_path,
                screen_size=menu_screen.get_size(),
            )
            set_language(config.get("language"))
            transition = ScreenTransition(ScreenID.TITLE)
        elif next_screen == ScreenID.GAMEPLAY:
            set_scaled_logical_size((SCREEN_WIDTH, SCREEN_HEIGHT))
            stage = incoming.stage
            seed_value = incoming.seed
            if stage is None:
                transition = ScreenTransition(ScreenID.TITLE)
            else:
                last_stage_id = stage.id
                render_assets = build_render_assets(stage.cell_size)
                try:
                    gs = _profiled_gameplay_screen if args.profile else gameplay_screen
                    transition = gs(
                        logical_screen,
                        clock,
                        config,
                        FPS,
                        stage,
                        show_pause_overlay=not debug_mode,
                        seed=seed_value,
                        render_assets=render_assets,
                        debug_mode=debug_mode,
                        show_fps=show_fps,
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
                render_assets = build_render_assets(stage.cell_size)
            else:
                render_assets = build_render_assets(DEFAULT_CELL_SIZE)
            transition = game_over_screen(
                logical_screen,
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
