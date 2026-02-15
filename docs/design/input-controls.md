# Input Controls

This chapter tracks player input behavior across keyboard, gamepad, and mouse.

## TODO: Mouse Steering During Gameplay

Status: phase 1 implemented (follow-up TODOs remain).

### Goal

- Allow mouse-based movement steering without breaking existing keyboard/gamepad play.
- Keep camera edge behavior consistent by basing mouse direction on player screen position.

### Planned Rules

1. Simultaneous availability
- Keyboard, gamepad, and mouse can all be enabled.
- No dedicated settings toggle is required for mouse steering.

2. Priority order per frame
- Evaluate keyboard/gamepad movement first.
- If keyboard or gamepad movement is non-zero, use that input and skip mouse movement evaluation.
- Only when both keyboard and gamepad movement are zero, evaluate mouse button state.

3. Mouse steering activation
- Mouse movement steering is active only while mouse button is pressed.
- Current default: left mouse button.
- While active, movement direction is computed from:
  - `mouse_screen_pos - player_screen_pos`

4. Deadzone
- If cursor is inside a small deadzone around the player, movement is treated as zero.

5. Camera edge consistency
- Input computation must never use screen center as steering origin.
- Always use current player screen position to avoid feel changes near map edges.

6. Cursor visibility
- Keep OS cursor hidden during gameplay (`pygame.mouse.set_visible(False)`).
- Draw an in-game `+` cursor at mouse position after mouse steering has been used.
- During active mouse steering (button held): show a thick yellow `+`.
- After button release: keep showing a thin white `+` for 10 seconds (wall-clock time, not frame count).
- Do not draw helper line from player to mouse, deadzone ring, or black outline circle around cursor.

7. Focus safety
- Mouse steering is ignored while the gameplay window is unfocused.
- Window focus state should gate mouse steering input to avoid unintended movement from platform-specific mouse event behavior.

## TODO Follow-ups

- Tune deadzone size and cursor visuals based on playtest feedback.
- Add focused tests for input priority and focus-gated mouse steering.
