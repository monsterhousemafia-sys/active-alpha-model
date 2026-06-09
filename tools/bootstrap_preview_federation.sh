#!/usr/bin/env bash
# Worker-Auto-Join — startet nach Login oder ACTIVE_ALPHA_WORKER_START.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1

if [[ ! -f "$ROOT/control/preview_worker_join.json" ]]; then
  exit 0
fi

echo "[worker] Preview-Federation Bundle erkannt"

EARLY_PY="python3"
HUB="$("$EARLY_PY" -c "
import json
from pathlib import Path
doc=json.loads(Path('$ROOT/control/preview_worker_join.json').read_text())
print((doc.get('hub_join_url') or '').rstrip('/'))
" 2>/dev/null || true)"
if [[ -z "$HUB" ]]; then
  echo "[FEHLER] hub_join_url fehlt in preview_worker_join.json" >&2
  exit 2
fi

if ! "$EARLY_PY" -c "
import urllib.request, sys
try:
    urllib.request.urlopen('${HUB}/api/health', timeout=8)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
  echo "[FEHLER] König-Hub nicht erreichbar: ${HUB}/api/health" >&2
  echo "        Firewall/LAN prüfen (ufw allow 17890/tcp auf König)" >&2
  exit 3
fi

if [[ ! -x "$PY" ]]; then
  echo "[worker] .venv fehlt — erstelle …"
  if ! command -v python3 >/dev/null; then
    echo "[FEHLER] python3 nicht installiert" >&2
    exit 1
  fi
  python3 -m venv "$ROOT/.venv"
  if [[ -f "$ROOT/requirements_active_alpha.txt" ]]; then
    "$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements_active_alpha.txt"
  fi
  PY="$ROOT/.venv/bin/python3"
fi

"$PY" -c "import analytics.preview_federation" 2>/dev/null || {
  echo "[FEHLER] Python-Abhängigkeiten unvollständig — pip install -r requirements_active_alpha.txt" >&2
  exit 4
}

bash "$ROOT/tools/setup_preview_worker_autostart.sh"

echo "[worker] Melde Leistung an König …"
"$PY" "$ROOT/tools/preview_federation_worker.py" --join-from-config --once --no-preview

systemctl --user start active-alpha-preview-worker.service 2>/dev/null || true
systemctl --user enable active-alpha-preview-worker.service 2>/dev/null || true

if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  xdg-open "${HUB%/}/" 2>/dev/null || true
fi

echo "[OK] Worker verbunden — Leistung wird zentral zusammengeführt"
