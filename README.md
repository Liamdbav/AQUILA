# AQUILA

Outil de packaging Python → exécutable protégé par Cython.

Glisse un fichier `.py` ou un dossier projet dans l'interface, choisis un dossier de sortie, et AQUILA produit un binaire obfusqué via Cython + PyInstaller.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Prérequis

- [Node.js](https://nodejs.org/) ≥ 18
- [Rust](https://rustup.rs/) stable
- [Python 3.12](https://www.python.org/) via [pyenv](https://github.com/pyenv/pyenv)

## Installation

```bash
git clone https://github.com/ton-handle/aquila.git
cd aquila

# Dépendances Node (Tauri CLI)
npm install

# Environnement Python
pyenv local 3.12
python -m venv .venv
source .venv/bin/activate
pip install -r python-core/requirements.txt

# Configuration des chemins locaux
./setup.sh
```

## Utilisation

```bash
npm run dev
```

1. Glisse un fichier `.py` ou un dossier projet dans la zone de dépôt (ou utilise les boutons de sélection)
2. Choisis le dossier de sortie
3. Clique sur **Générer le .exe**
4. Suis la progression dans les logs — le binaire apparaît dans le dossier choisi

## Architecture

```
src/              — Interface (HTML/JS vanilla, Tauri webview)
src-tauri/        — Backend Rust, commandes Tauri (lib.rs)
python-core/      — Pipeline de packaging (packager.py)
```

Le pipeline Python suit ces étapes : détection du point d'entrée → collecte des fichiers → compilation Cython → génération du lanceur → PyInstaller `--onefile`.

---

<div align="center">

Fait avec soin par **Liam** - License MIT — voir [LICENSE](LICENSE)

[![Follow on X](https://img.shields.io/badge/Follow-%40Liamdbav-000000?style=flat-square&logo=x&logoColor=white)](https://x.com/Liamdbav)

</div>
