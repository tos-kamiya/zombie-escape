from __future__ import annotations

import sys
import traceback  # For error reporting
from typing import Any

import pygame

try:
    from .__about__ import __version__
except Exception:  # pragma: no cover - fallback version
    __version__ = "0.0.0-unknown"
from .config import load_config, save_config
from .constants import (
    CAR_SPEED,
    DEFAULT_WINDOW_SCALE,
    FPS,
    RENDER_ASSETS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SURVIVOR_MAX_SAFE_PASSENGERS,
    SURVIVOR_MIN_SPEED_FACTOR,
)
from .localization import set_language
from .models import GameData, Stage, STAGES, DEFAULT_STAGE_ID
from .screens import ScreenID, ScreenTransition, apply_window_scale
from .screens.game_over import game_over_screen
from .screens.settings import settings_screen
from .screens.title import title_screen
from .gameplay.logic import calculate_car_speed_for_passengers

# --- Main Entry Point ---
def main() -> None:
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

    hide_pause_overlay = "--hide-pause-overlay" in sys.argv

    config: dict[str, Any]
    config, config_path = load_config()
    if not config_path.exists():
        save_config(config, config_path)
    set_language(config.get("language"))

    next_screen = ScreenID.TITLE
    pending_stage: Stage | None = None
    pending_game_data: GameData | None = None
    pending_config: dict[str, Any] | None = None
    running = True

    while running:
        transition: ScreenTransition | None = None

        if next_screen == ScreenID.TITLE:
            transition = title_screen(
                screen,
                clock,
                config,
                FPS,
                stages=STAGES,
                default_stage_id=DEFAULT_STAGE_ID,
                screen_size=(SCREEN_WIDTH, SCREEN_HEIGHT),
            )
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
            if stage is None:
                transition = ScreenTransition(ScreenID.TITLE)
            else:
                try:
                    transition = gameplay_screen(
                        screen,
                        clock,
                        config,
                        FPS,
                        stage,
                        show_pause_overlay=not hide_pause_overlay,
                        render_assets=RENDER_ASSETS,
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
        next_screen = transition.next_screen

    pygame.quit()  # Quit pygame only once at the very end of main
    sys.exit()  # Exit the script

if __name__ == "__main__":
    main()
