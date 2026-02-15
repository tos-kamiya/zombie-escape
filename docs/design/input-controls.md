# Input Controls

This chapter tracks player input behavior across keyboard, gamepad, and mouse.

## Status

- Gameplay mouse steering: DONE
- Menu mouse navigation (title/settings/game over/pause): DONE
- Menu mouse navigation progress:
  - DONE: title screen, settings screen, game-over screen, in-game pause menu
- Input UI abstraction (mouse guard + clickable map): INPROGRESS

## Mouse Steering During Gameplay

### Goal

- Allow mouse-based movement steering without breaking existing keyboard/gamepad play.
- Keep camera edge behavior consistent by basing mouse direction on player screen position.

### Rules

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
- Mouse acceleration trigger is also available while holding left mouse button near player center.
- Acceleration radius is smaller than movement deadzone radius to keep intent clear.

4. Deadzone
- If cursor is inside a small deadzone around the player, movement is treated as zero.

5. Camera edge consistency
- Input computation must never use screen center as steering origin.
- Always use current player screen position to avoid feel changes near map edges.

6. Cursor visibility
- Keep OS cursor hidden during gameplay (`pygame.mouse.set_visible(False)`).
- Draw an in-game `+` cursor at mouse position after mouse steering has been used.
- During active mouse steering (button held): show a thick yellow `+`.
- Show a thin white `+` for 1.5 seconds (wall-clock time) after any of:
  - button release after mouse steering
  - game start
  - cursor movement of 10px or more between frames
- Do not draw helper line from player to mouse, deadzone ring, or black outline circle around cursor.

7. Focus safety
- Mouse steering is ignored while the gameplay window is unfocused.
- Window focus state should gate mouse steering input to avoid unintended movement from platform-specific mouse event behavior.

## Mouse Navigation In Menu Screens (INPROGRESS)

### Scope

- Title screen
- Settings screen
- Game-over screen
- In-game pause menu

### Rules

1. Cursor visibility
- Show OS mouse cursor on the screens in scope.
- Fullscreen mode must not force-hide OS cursor globally; each screen controls visibility explicitly.
- Keep keyboard/gamepad navigation enabled at the same time.

2. Hover and selection ownership
- Mouse motion updates the current selection by hover.
- Keyboard/gamepad directional input can still move selection.
- The most recent device interaction owns the visible selection.

3. Click activation
- Activate items on left-button release (`MOUSEBUTTONUP`).
- Do not activate disabled/locked items.

4. Focus safety
- Ignore hover updates and click activation while the window is unfocused.
- After focus is regained, suppress mouse activation briefly to avoid accidental click-through.
- Minimum guard: one frame after focus regain.

5. Pause screen behavior
- Pause provides explicit selectable menu items (`Resume`, `Return to Title`) so mouse navigation has concrete targets.
- While paused, OS cursor is visible and menu items are selectable by hover + left-button release.
- In `--debug` mode (pause overlay hidden), left-button release while paused acts as `Resume`.
- During gameplay (not paused), mouse users can enter pause by moving the cursor into one of the four corner hotspot markers in the mouse-movable area.
- If pause hotspot intent and mouse acceleration intent conflict, pause hotspot behavior takes priority.

6. Game-over menu presentation
- Game-over screen uses explicit selectable buttons (`Return to Title`, `Retry Stage`) instead of a separate key-help line.
- Each button label includes one representative shortcut hint (for example: `ESC/SOUTH`, `R/START`).

## Follow-ups

- Tune gameplay deadzone and cursor visuals based on playtest feedback.
- Tune mouse acceleration center radius based on playtest feedback.
- Define final pause menu item set and layout.
- Consolidate repeated menu mouse-input code via shared input utilities.
- Add focused tests for input priority and focus-gated mouse interactions.
