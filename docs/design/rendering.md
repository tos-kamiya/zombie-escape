# Rendering

Supporting modules:
- `src/zombie_escape/render_assets.py` (procedural sprite/icon construction used by renderers and UI)
- `src/zombie_escape/colors.py` (palette selection and ambient color policy)

## Render Pipeline (`render/core.py`)

`draw(...)` performs rendering in this order:

1. Fill background with ambient color.
2. Draw floor/playfield patterns.
3. Draw pitfall visuals (depth, gradients, cut surfaces).
4. Compose shadow layer (walls + entities).
5. Draw fading footprints.
6. Draw sprites with camera transforms.
7. Draw variant markers (tracker/wall-hugger/lineformer/solitary visuals).
8. Draw hint arrow.
9. Draw fog (`hard` mask + `soft` hatch overlay).
10. Draw HUD/status/objective text.

## Layering

- Sprite layering is driven by `LAYER_*` constants.
- Outside-area entities generally skip shadow rendering.
- Jumping entities draw detached/offset shadows for airborne feel.

## HUD

- Status bar shows settings flags, stage index, and seed.
- Debug lineformer display includes real-entity and marker totals.
- Timed messages support alignment mode and stay readable during fade transitions.

## Overviews (`render/overview.py`)

- `draw_level_overview()`: game-over map overview cache.
- `draw_debug_overview()`: full-map debug visualization with camera frame.
