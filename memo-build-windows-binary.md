# Memo: Build Windows binary with PyInstaller

This is a personal memo describing how to build a Windows binary
(one-folder, zip distribution) for **zombie-escape**.

## 1. Environment

- Windows 11 (64-bit)
- Python 3.13 (64-bit)

## 2. Prepare an entry point for PyInstaller

Create a temporary file `./pyinstaller_main.py`
(not committed to the repository) with the following content:

```python
# pyinstaller_main.py
from __future__ import annotations

from zombie_escape import main

if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback, pathlib
        log = pathlib.Path.home() / "zombie_escape_error.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        raise
```

## 3. Build

```bat
cd <project-dir>
python -m venv venv
venv\Scripts\activate.bat

pip install pygame
pip install platformdirs
pip install python-i18n
pip install pyinstaller

pyinstaller --clean -y -n zombie-escape --onedir ^
  --paths src ^
  --collect-submodules zombie_escape ^
  --add-data "src\zombie_escape\locales;zombie_escape\locales" ^
  --add-data "src\zombie_escape\assets;zombie_escape\assets" ^
  --windowed ^
  pyinstaller_main.py
```

## 4. Check

```bat
.\dist\zombie-escape\zombie-escape.exe
```

## Notes

* One-folder mode is used for stability.
* Distribution is done by zipping the entire `dist/zombie-escape/` directory.
* For debugging, rebuild without `--windowed`.
