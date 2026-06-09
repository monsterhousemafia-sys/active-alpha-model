#!/usr/bin/env bash
# USB-Watcher: auto install-local + Spread (systemd timer/path).
set -euo pipefail

DEST="${AA_USB_INSTALL_DEST:-$HOME/active_alpha_model}"
if [[ -f "$DEST/tools/king_ops.sh" ]]; then
  ROOT="$DEST"
elif [[ -n "${AA_PROJECT_ROOT:-}" && -f "${AA_PROJECT_ROOT}/tools/king_ops.sh" ]]; then
  ROOT="$AA_PROJECT_ROOT"
else
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"

exec "$PY" -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT')
from analytics.usb_autostart import run_usb_autostart_tick
doc = run_usb_autostart_tick(Path('$ROOT'), persist=True)
print(json.dumps({'headline_de': doc.get('headline_de'), 'action': doc.get('action'), 'ok': doc.get('ok')}, ensure_ascii=False))
sys.exit(0 if doc.get('ok', True) else 1)
"
