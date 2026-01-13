from __future__ import annotations

import argparse
import sys
import traceback  # For error reporting
from typing import Any, Tuple

import pygame

try:
    from .__about__ import __version__
except Exception:  # pragma: no cover - fallback version
    __version__ = "0.0.0-unknown"
from .config import load_config, save_config
from .gameplay_constants import (
    CAR_SPEED,
    SURVIVOR_MAX_SAFE_PASSENGERS,
    SURVIVOR_MIN_SPEED_FACTOR,
)
from .render_constants import RENDER_ASSETS
from .screen_constants import (
    DEFAULT_WINDOW_SCALE,
    FPS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from .localization import set_language
from .models import GameData, Stage
from .stage_constants import DEFAULT_STAGE_ID, STAGES
from .screens import ScreenID, ScreenTransition, apply_window_scale
from .screens.game_over import game_over_screen
from .screens.settings import settings_screen
from .screens.title import MAX_SEED_DIGITS, title_screen
from .gameplay.logic import calculate_car_speed_for_passengers


def _parse_cli_args(argv: list[str]) -> Tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--debug", action="store_true", help="Enable debugging aids for Stage 5 and hide pause overlay")
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
    try:
        pygame.font.init()
    except pygame.error as e:
        print(f"Pygame font failed to initialize: {e}")
        # Font errors are often non-fatal, continue without fonts or handle gracefully

    from .screens.gameplay import gameplay_screen

    apply_window_scale(DEFAULT_WINDOW_SCALE)
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

    next_screen = ScreenID.TITLE
    pending_stage: Stage | None = None
    pending_game_data: GameData | None = None
    pending_config: dict[str, Any] | None = None
    pending_seed: int | None = None
    running = True

    while running:
        transition: ScreenTransition | None = None

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
            stage = pending_stage
            pending_stage = None
            seed_value = pending_seed
            pending_seed = None
            if stage is None:
                transition = ScreenTransition(ScreenID.TITLE)
            else:
                last_stage_id = stage.id
                try:
                    transition = gameplay_screen(
                        screen,
                        clock,
                        config,
                        FPS,
                        stage,
                        show_pause_overlay=not debug_mode,
                        seed=seed_value,
                        render_assets=RENDER_ASSETS,
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
            game_data = pending_game_data
            stage = pending_stage
            config_payload = pending_config
            pending_game_data = None
            pending_stage = None
            pending_config = None
            transition = game_over_screen(
                screen,
                clock,
                config_payload,
                FPS,
                game_data=game_data,
                stage=stage,
                render_assets=RENDER_ASSETS,
            )
        elif next_screen == ScreenID.EXIT:
            break
        else:
            transition = ScreenTransition(ScreenID.TITLE)

        if not transition:
            break

        pending_stage = transition.stage
        pending_game_data = transition.game_data
        pending_config = transition.config
        pending_seed = transition.seed
        if transition.next_screen == ScreenID.GAMEPLAY:
            title_seed_text = cli_seed_text
            title_seed_is_auto = cli_seed_is_auto
        next_screen = transition.next_screen

    pygame.quit()  # Quit pygame only once at the very end of main
    sys.exit()  # Exit the script


if __name__ == "__main__":
    main()
