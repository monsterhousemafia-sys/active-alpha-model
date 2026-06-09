#!/usr/bin/env bash
# Session-Autostart: Preview-HTML als Browser-Fenster (nach Anmeldung).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  exit 0
fi

export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"
export AA_PREVIEW_AUTOSTART=1

if [[ -f "$ROOT/control/preview_worker_join.json" ]]; then
  exec bash "$ROOT/tools/bootstrap_preview_federation.sh"
fi

# Dedup: frischer Lauf nur wenn >20 min — sonst sofort HTML öffnen.
exec "$PY" "$ROOT/tools/run_gui_preview.py" --open-html
