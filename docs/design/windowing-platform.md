# Windowing and Platform

Primary implementation: `src/zombie_escape/windowing.py`

## Fullscreen and Logical Resolution

- Toggle fullscreen/windowed with `F` (startup is windowed).
- Fullscreen selection tries SDL2 display detection from current window location.
- Falls back to generic fullscreen mode when display detection fails.
- Window restore tries last window position (may be ignored by some Wayland environments).
- Base logical resolution is `400x300`; presentation scales to OS window size.

## Presentation Path

- Game and menu both render to `400x300` logical surfaces.
- `present()` scales to actual window while preserving aspect.
- If `pygame.SCALED` is unavailable, fallback path letterboxes manually.
- Window recreation occurs when `set_mode()` is needed:
  - fullscreen toggle
  - window scale changes
  - logical-size related mode changes

## Platform Stability Notes

- Rapid resize-key input on Windows can overload repeated `set_mode()` calls.
- `apply_window_scale()` includes cooldown/deferred apply logic.
- Pending scale updates can be applied immediately after resize events.

## Runtime Environment Switches

- `ZOMBIE_ESCAPE_VSYNC=0/1`: toggles vsync flag in display mode setup.
- `ZOMBIE_ESCAPE_BUSY_LOOP=1`: uses `Clock.tick_busy_loop()` for frame timing stability.

## Profiling Mode

- `--profile` enables runtime profiling toggled by `F10`.
- Saves `profile.prof` and top summary text `profile.txt` on stop.
