# Input Controls

This chapter tracks player input behavior across keyboard, gamepad, and mouse.

## TODO: Mouse Steering During Gameplay

Status: planned, not implemented yet.

### Goal

- Allow mouse-based movement steering without breaking existing keyboard/gamepad play.
- Keep camera edge behavior consistent by basing mouse direction on player screen position.

### Planned Rules

1. Simultaneous availability
- Keyboard, gamepad, and mouse can all be enabled.

2. Priority order per frame
- Evaluate keyboard/gamepad movement first.
- If keyboard or gamepad movement is non-zero, use that input and skip mouse movement evaluation.
- Only when both keyboard and gamepad movement are zero, evaluate mouse button state.

3. Mouse steering activation
- Mouse movement steering is active only while mouse button is pressed.
- Recommended default: left mouse button.
- While active, movement direction is computed from:
  - `mouse_screen_pos - player_screen_pos`

4. Deadzone
- If cursor is inside a small deadzone around the player, movement is treated as zero.

5. Camera edge consistency
- Input computation must never use screen center as steering origin.
- Always use current player screen position to avoid feel changes near map edges.

6. Cursor visibility
- During mouse steering, show a clear in-game cursor style suitable for gameplay readability.
- Outside active mouse steering, normal menu/window mouse usage should remain unhindered.

