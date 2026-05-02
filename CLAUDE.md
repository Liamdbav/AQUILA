# AQUILA

Outil de packaging Python → .exe protégé par Cython.

## Stack
- Tauri v2 (fenêtre native macOS)
- UI HTML/JS vanilla
- Python 3.12 via pyenv (venv isolé : ~/Projects/aquila/.venv)
- Cython 3.x + PyInstaller 6.x

## Architecture
- src/ : UI drag & drop (fenêtre Tauri)
- src-tauri/ : binaire Rust + commandes Tauri
- python-core/ : pipeline de packaging Python

## Commandes
- npm run dev : lancer en développement
- npm run tauri build : builder le .dmg macOS
- source .venv/bin/activate : activer le venv Python

## Conventions
- Toutes les commandes Tauri sont dans src-tauri/src/lib.rs
- Le pipeline Python est exclusivement dans python-core/packager.py
- Jamais de logique métier dans le frontend JS
