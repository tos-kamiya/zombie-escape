# Rendering

## Fire/Metal Floor Rendering

- Fire floor visual:
  - Fire floor tiles are rendered as an animated floor feature.
  - Animation uses a 3-frame loop.
- Metal floor visual:
  - `metal_floor_cells` are rendered as a distinct industrial floor tile.
  - Behavior remains identical to normal floor; this is a visual transition layer
    around fire floor regions.
- Puddle floor visual:
  - Puddle tiles render additive ripple rings.
  - Puddle animation uses a 12-frame loop.
  - Timing is aligned so one puddle loop matches four fire-floor loops
    (fire: `3 frames x 4`, puddle: `12 frames x 1`).
- Draw-order intent:
  - Fire/metal/puddle floor rendering is handled in world-tile pass, before entities and fog.

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

### Fog Notes

- Fog overlay generation (`render/fog.py`) now uses a 16x16 Bayer matrix for
  hatch thresholding.
- Fog edge quality is improved by rendering fog overlays at
  `FOG_LAYER_AA_SCALE` resolution, then downsampling to gameplay resolution.
- Fade, hatch, and edge-feather alpha generation are numpy-based for faster
  precomputation.

`core.py` delegates concrete rendering work to split modules:
- `render/world_tiles.py`
- `render/entity_layer.py`
- `render/fog.py`
- `render/fx.py`
- `render/text_overlay.py`
- `render/shadows.py`
- `render/hud.py`

## Layering

- Sprite layering is driven by `LAYER_*` constants.
- Outside-area entities generally skip shadow rendering.
- Entity shadows are rendered in one pass with a uniform alpha policy.
  Sprites that define `shadow_radius` are included; there is no per-entity-type
  shadow alpha override in `core.py`.
- Jumping entities draw detached/offset shadows for airborne feel.

## HUD

- Status bar shows settings flags, stage index, and seed.
- Zombie debug summary is built once (`build_zombie_debug_counts_text`) and rendered
  via `_draw_status_bar` in both gameplay and overview paths.
- Debug lineformer display includes real-entity and marker totals.
- Lineformer train markers use cached directional sprites and are blitted per marker (instead of rebuilding arm lines every frame).
- Tracker zombie dogs use a baked nose-line marker in their directional sprites
  (not a separate post-sprite overlay pass).
- Timed messages support alignment mode and stay readable during fade transitions.

## Variant Marker Sprite Strategy

- Zombie variant markers are selected from prebuilt directional sprite caches
  (instead of per-frame overlay drawing).
- Wall-hugger marker states are modeled as three discrete states:
  `none`, `right-hand`, `left-hand`.
- Lineformer arm direction is quantized to 16 bins and selected by
  `(facing_bin, target_bin16)` key.
- Tracker/solitary markers are treated as static per-facing overlays and baked
  into directional images.

## Fog Cache File

- Add an offline fog-cache tool that precomputes data close to runtime fog
  overlays and writes it to a file.
- Target profiles are `DARK0`, `DARK1`, and `DARK2`.
- Cache payload stores alpha planes as `numpy.uint8` arrays (not pygame surface
  binary) so runtime reconstructs `Surface` objects from stable numeric data.
- Runtime first tries bundled resource cache files
  (`assets/fog_cache/*.npz`) for each profile, then user cache.
- Startup check requires all fog cache profiles to load successfully before
  entering the title screen.
- In normal game execution, fog overlays are expected to come from loaded cache
  files; no title/gameplay prewarm generation path is used.
- Cache-key metadata includes rendering parameters and runtime version info so
  incompatible cache files are ignored safely.

## Overviews (`overview.py`)

- `draw_level_overview()`: core full-map drawing pass (terrain, entities, zombies).
- `draw_debug_overview()`: scaled full-map visualization with camera frame and status bar.
- Game-over overview and debug overview share the same `draw_debug_overview()`
  rendering path.
- Puddle cells are drawn as simple circular markers (not animated ripple rings)
  for readability at reduced scale.
