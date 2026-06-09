#!/usr/bin/env bash
# Einmalig im echten Terminal (sudo-Passwort nötig):
#   bash tools/install_whatsapp_deps.sh
set -euo pipefail
_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tools/r3_common.sh
source "$_ROOT/tools/r3_common.sh"
r3_init

echo "=== WhatsApp Auto-Send — System-Deps ==="
if command -v xclip >/dev/null 2>&1 && command -v xdotool >/dev/null 2>&1; then
  echo "[OK] xclip + xdotool bereits installiert"
else
  if [ -t 0 ]; then
    sudo apt-get update -qq
    sudo apt-get install -y xclip xdotool wl-clipboard xsel
  elif command -v pkexec >/dev/null 2>&1; then
    pkexec apt-get install -y xclip xdotool wl-clipboard xsel
  else
    echo "[WARN] xclip/xdotool fehlen — Fallback: python-xlib + wl-copy (pip/apt optional)"
  fi
fi
bash "$_ROOT/tools/setup_whatsapp_auto.sh" install
echo ""
echo "=== Start ==="
echo "  bash tools/king_ops.sh whatsapp durch"
