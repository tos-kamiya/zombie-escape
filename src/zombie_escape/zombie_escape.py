import sys
import traceback  # For error reporting
from typing import Optional

import pygame
from pygame import surface

try:
    from .__about__ import __version__
except Exception:  # pragma: no cover - fallback version
    __version__ = "0.0.0-unknown"
from .config import load_config, save_config
from .constants import (
    DEFAULT_WINDOW_SCALE,
    FPS,
    RENDER_ASSETS,
    RENDER_SCREEN_HEIGHT,
    RENDER_SCREEN_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WINDOW_SCALE_MAX,
    WINDOW_SCALE_MIN,
)
from .i18n import set_language, translate as _
from .models import GameData, STAGES, DEFAULT_STAGE_ID
from .screens import ScreenID, ScreenTransition
from .screens.game_over import game_over_screen
from .screens.settings import settings_screen
from .screens.title import title_screen

current_window_scale = DEFAULT_WINDOW_SCALE  # Applied to the OS window only

# --- Window scaling helpers ---
def apply_window_scale(
    scale: float, game_data: Optional[GameData] = None
) -> surface.Surface:
    """Resize the OS window; the logical render surface stays at the default size."""
    global current_window_scale

    clamped_scale = max(WINDOW_SCALE_MIN, min(WINDOW_SCALE_MAX, scale))
    current_window_scale = clamped_scale

    window_width = max(1, int(RENDER_SCREEN_WIDTH * current_window_scale))
    window_height = max(1, int(RENDER_SCREEN_HEIGHT * current_window_scale))

    new_window = pygame.display.set_mode((window_width, window_height))
    pygame.display.set_caption(
        f"{_('game.title')} v{__version__} ({window_width}x{window_height})"
    )

    if game_data is not None:
        # Invalidate cached overview so it can be re-scaled next time it's drawn
        game_data.state.overview_created = False

    return new_window

def nudge_window_scale(
    multiplier: float, game_data: Optional[dict] = None
) -> surface.Surface:
    """Change window scale relative to the current setting."""
    target_scale = current_window_scale * multiplier
    return apply_window_scale(target_scale, game_data)

def present(logical_surface: surface.Surface) -> None:
    """Scale the logical surface directly to the window and flip buffers."""
    window = pygame.display.get_surface()
    if window is None:
        return
    window_size = window.get_size()
    logical_size = logical_surface.get_size()
    if window_size == logical_size:
        window.blit(logical_surface, (0, 0))
    else:
        pygame.transform.scale(logical_surface, window_size, window)
    pygame.display.flip()


# --- Game State Function (Contains the main game loop) ---

# --- Splash & Menu Functions ---

# --- Main Entry Point ---
def main():
    pygame.init()
    try:
        pygame.font.init()
    except pygame.error as e:
        print(f"Pygame font failed to initialize: {e}")
        # Font errors are often non-fatal, continue without fonts or handle gracefully

    from .screens.gameplay import gameplay_screen

    apply_window_scale(current_window_scale)
    screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert_alpha()
    clock = pygame.time.Clock()

    hide_pause_overlay = "--hide-pause-overlay" in sys.argv

    config, config_path = load_config()
    if not config_path.exists():
        save_config(config, config_path)
    set_language(config.get("language"))

    next_screen = ScreenID.TITLE
    payload: dict[str, object] = {}
    running = True

    while running:
        transition: ScreenTransition | None = None

        if next_screen == ScreenID.TITLE:
            transition = title_screen(
                screen,
                clock,
                config,
                STAGES,
                DEFAULT_STAGE_ID,
                screen_size=(SCREEN_WIDTH, SCREEN_HEIGHT),
                fps=FPS,
                window_scale_fn=nudge_window_scale,
                present_fn=present,
            )
        elif next_screen == ScreenID.SETTINGS:
            config = settings_screen(
                screen,
                clock,
                config,
                config_path,
                screen_size=(SCREEN_WIDTH, SCREEN_HEIGHT),
                fps=FPS,
                present_fn=present,
                window_scale_fn=nudge_window_scale,
            )
            set_language(config.get("language"))
            transition = ScreenTransition(ScreenID.TITLE)
        elif next_screen == ScreenID.GAMEPLAY:
            stage = payload.get("stage") if payload else None
            if stage is None:
                transition = ScreenTransition(ScreenID.TITLE)
            else:
                try:
                    transition = gameplay_screen(
                        screen,
                        clock,
                        config,
                        stage,
                        show_pause_overlay=not hide_pause_overlay,
                        fps=FPS,
                        render_assets=RENDER_ASSETS,
                        present_fn=present,
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
            transition = game_over_screen(
                screen,
                clock,
                payload,
                render_assets=RENDER_ASSETS,
                fps=FPS,
                present_fn=present,
            )
        elif next_screen == ScreenID.EXIT:
            break
        else:
            transition = ScreenTransition(ScreenID.TITLE)

        if not transition:
            break

        payload = transition.payload or {}
        next_screen = transition.next_screen

    pygame.quit()  # Quit pygame only once at the very end of main
    sys.exit()  # Exit the script

if __name__ == "__main__":
    main()
