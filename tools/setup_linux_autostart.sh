#!/usr/bin/env bash
# R3 OS — Desktop-Menü (kein Legacy-Autostart).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
LAUNCHER="$ROOT/run_marktanalyse_linux.sh"
DESKTOP_ID="active-alpha-marktanalyse.desktop"

if [[ ! -x "$LAUNCHER" ]]; then
  echo "[FEHLER] Launcher fehlt: $LAUNCHER" >&2
  exit 1
fi

mkdir -p "$AUTOSTART_DIR" "$APPS_DIR"

rm -f "$AUTOSTART_DIR/$DESKTOP_ID" "$ROOT/Marktanalyse.desktop" "$APPS_DIR/Marktanalyse.desktop"
chmod +x "$LAUNCHER"
bash "$ROOT/tools/setup_r3_desktop_os.sh"
