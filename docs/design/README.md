# Design Docs

This directory contains the canonical design documentation for `zombie-escape`.
English is the source of truth.

## Contents

- `docs/design/architecture.md`: Module layout and screen transitions.
- `docs/design/data-models.md`: Core dataclasses (`GameData`, `ProgressState`, `Stage`, etc.).
- `docs/design/entities.md`: Entity behavior and gameplay objects.
- `docs/design/ai-zombies.md`: Zombie variants and AI behavior.
- `docs/design/gameplay-flow.md`: Initialization, spawn, update, and interaction flow.
- `docs/design/title-screen.md`: Title menu behavior and stage-select icon ordering rules.
- `docs/design/rendering.md`: Render pipeline, fog, shadows, HUD.
- `docs/design/windowing-platform.md`: Window/fullscreen behavior and platform notes.
- `docs/design/level-generation.md`: Blueprint generation and connectivity validation.
- `docs/design/config-and-progress.md`: Config, progress save data, and seed handling.
- `docs/design/localization.md`: Localization architecture and schema rules.
- `docs/design/constants-index.md`: Index of important constant modules.

## Legacy Japanese Doc

- `docs/design/legacy/design.ja.md`: Archived full Japanese design memo from git history.

## Update Rule

- Update only the chapter that matches your change.
- If chapter boundaries change, update this index in the same PR.
