#!/usr/bin/env bash
# Plan B: lokale Upload-Ordner im Dateimanager öffnen
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS="$ROOT/docs"
TOOLS="$ROOT/tools"

open_path() {
  local p="$1"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$p" >/dev/null 2>&1 &
  elif command -v nautilus >/dev/null 2>&1; then
    nautilus "$p" >/dev/null 2>&1 &
  elif command -v dolphin >/dev/null 2>&1; then
    dolphin "$p" >/dev/null 2>&1 &
  elif command -v thunar >/dev/null 2>&1; then
    thunar "$p" >/dev/null 2>&1 &
  else
    echo "Ordner: $p"
    return 1
  fi
  return 0
}

echo "=== Plan B — lokale Ordner öffnen ==="
echo "docs:  $DOCS"
echo "tools: $TOOLS"
echo ""

open_path "$DOCS" && echo "[OK] docs geöffnet"
sleep 0.8
open_path "$TOOLS" && echo "[OK] tools geöffnet"
sleep 0.5
open_path "$DOCS/GITHUB_SYNC_PLAN_B.md" && echo "[OK] GITHUB_SYNC_PLAN_B.md geöffnet"

echo ""
echo "Upload-Ziele siehe: $DOCS/GITHUB_SYNC_PLAN_B.md"
echo "GitHub: https://github.com/monsterhousemafia-sys/active-alpha-model"
