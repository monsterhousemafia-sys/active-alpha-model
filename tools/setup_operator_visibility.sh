#!/usr/bin/env bash
# R3 OS — Sichtbarkeit (delegiert an setup_r3_desktop_os).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
BIN_DIR="${HOME}/.local/bin"
SHARE_DIR="${HOME}/.local/share/active-alpha"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
mkdir -p "$BIN_DIR" "$SHARE_DIR" "$AUTOSTART"

exec bash "$ROOT/tools/setup_r3_desktop_os.sh"
