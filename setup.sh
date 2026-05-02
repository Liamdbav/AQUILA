#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$PROJECT_DIR/aquila.local.json"

echo ""
echo "  ▲  AQUILA — Configuration"
echo ""

# --- Python ---------------------------------------------------------------
DETECTED="$PROJECT_DIR/.venv/bin/python"
if [ -f "$DETECTED" ]; then
    echo "  Python détecté : $DETECTED"
    read -rp "  Utiliser ce chemin ? [O/n] : " CHOICE
    if [[ "$CHOICE" =~ ^[Nn]$ ]]; then
        read -rp "  Chemin vers python : " PYTHON_PATH
    else
        PYTHON_PATH="$DETECTED"
    fi
else
    echo "  Aucun venv trouvé dans .venv/"
    read -rp "  Chemin vers python (ex: /usr/bin/python3) : " PYTHON_PATH
fi

if ! "$PYTHON_PATH" --version &>/dev/null; then
    echo "  ✗  Python introuvable : $PYTHON_PATH"
    exit 1
fi

# --- Packager (fixe, relatif au projet) ------------------------------------
PACKAGER_PATH="$PROJECT_DIR/python-core/packager.py"
if [ ! -f "$PACKAGER_PATH" ]; then
    echo "  ✗  packager.py introuvable : $PACKAGER_PATH"
    exit 1
fi

# --- Écriture config -------------------------------------------------------
cat > "$CONFIG_FILE" <<EOF
{
  "python": "$PYTHON_PATH",
  "packager": "$PACKAGER_PATH"
}
EOF

PYVER=$("$PYTHON_PATH" --version 2>&1)
echo ""
echo "  ✓  aquila.local.json créé"
echo "  ✓  Python  : $PYTHON_PATH  ($PYVER)"
echo "  ✓  Packager: $PACKAGER_PATH"
echo ""
echo "  → Lancez : npm run dev"
echo ""
