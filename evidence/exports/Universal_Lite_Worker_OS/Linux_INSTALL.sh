#!/bin/bash
# Universal Lite Worker OS — lokale Installation + Start
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL="${ULWO_HOME:-$HOME/.local/share/ulwo-worker}"
mkdir -p "$INSTALL"
rsync -a "$DIR/" "$INSTALL/"
chmod +x "$INSTALL/Linux_START.sh" "$INSTALL/worker.py" 2>/dev/null || true
cat > "$HOME/.local/bin/ulwo" <<EOF
#!/usr/bin/env bash
exec bash "$INSTALL/Linux_START.sh"
EOF
chmod +x "$HOME/.local/bin/ulwo" 2>/dev/null || true
echo "[OK] Universal Lite Worker OS installiert unter $INSTALL"
echo "[OK] Start: ulwo  oder  $INSTALL/Linux_START.sh"
exec bash "$INSTALL/Linux_START.sh"
