# Localization

- `localization.py` wraps `python-i18n` for UI text lookup.
- Locale resources are stored in `src/zombie_escape/locales/ui.*.json`.
- `translate()` is the main access path.
- Locale-specific font settings and scaling are supported.
- Schema parity across locale files is mandatory and validated by `tests/test_localization_schema.py`.
