#!/usr/bin/env bash
# König: Projektordner für Worker vorbereiten (heute verschicken).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(readlink -f "$ROOT")"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"

DEST_ARG="${1:-}"
if [[ -z "$DEST_ARG" ]]; then
  DEST_ARG="$(dirname "$ROOT")/active_alpha_model_worker_$(date +%Y%m%d)"
fi
if ! DEST="$("$PY" -c "
import sys
from pathlib import Path
sys.path.insert(0, '$ROOT')
from analytics.worker_export_sync import validate_worker_export_dest
dest = validate_worker_export_dest(Path('$ROOT'), Path('${DEST_ARG}'))
dest.parent.mkdir(parents=True, exist_ok=True)
print(dest)
")"; then
  echo "[FEHLER] Ungültiges Export-Ziel: ${DEST_ARG}" >&2
  echo "[FEHLER] Ziel muss außerhalb des Projektordners liegen (kein Unterordner von $ROOT)." >&2
  exit 1
fi

echo "[export] Hub sicherstellen …"
"$PY" "$ROOT/tools/preview_hub.py" --ensure 2>/dev/null || true

echo "[export] Worker-Konfiguration schreiben …"
OUT="$("$PY" -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT')
from analytics.preview_federation import prepare_worker_bundle_config
from tools.preview_hub import ensure_hub_running
r = Path('$ROOT')
ensure_hub_running(r, restart=False)
cfg = prepare_worker_bundle_config(r)
print(json.dumps(cfg, ensure_ascii=False))
")"

HUB="$(echo "$OUT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("hub_join_url") or "")')"

echo "[export] Ziel: $DEST"
RSYNC_EXCLUDES="$("$PY" -c "
import sys
from pathlib import Path
sys.path.insert(0, '$ROOT')
from analytics.worker_export_sync import WORKER_BUNDLE_RSYNC_EXCLUDES
print(' '.join('--exclude ' + repr(x) for x in WORKER_BUNDLE_RSYNC_EXCLUDES))
")"
# shellcheck disable=SC2086
rsync -aH --info=progress2 $RSYNC_EXCLUDES "$ROOT/" "$DEST/"

echo "$OUT" | "$PY" -c "
import json, sys
from pathlib import Path
cfg = json.load(sys.stdin)
dest = Path('$DEST')
(dest / 'control').mkdir(parents=True, exist_ok=True)
(dest / 'control/preview_worker_join.json').write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
readme = '''Active Alpha — Kollektive Rechenrevolution (Worker-Bundle)
============================================================
Lies zuerst: control/WORKER_AUFKLAERUNG_DE.md

Kurz: Du stellst CPU-Leistung bereit — kein Geld, kein Broker-Zugang.

Start:
  ./ACTIVE_ALPHA_WORKER_START.sh
  (oder neu anmelden — Autostart)

Command Center König: ''' + str(cfg.get('hub_join_url') or '') + '''

Raus aus der Kollektiv-Leistung:
  systemctl --user stop active-alpha-preview-worker.service
'''
(dest / 'README_WORKER_DE.txt').write_text(readme, encoding='utf-8')
auf = Path('$ROOT') / 'control/WORKER_AUFKLAERUNG_DE.md'
if auf.is_file():
    (dest / 'control/WORKER_AUFKLAERUNG_DE.md').write_text(auf.read_text(encoding='utf-8'), encoding='utf-8')
"

chmod +x "$DEST/ACTIVE_ALPHA_WORKER_START.sh" "$DEST/tools/bootstrap_preview_federation.sh" 2>/dev/null || true

echo ""
echo "[OK] Worker-Bundle: $DEST"
echo "[OK] König-Hub:     $HUB"
echo "[OK] Auf Worker-PC:  cd '$DEST' && ./ACTIVE_ALPHA_WORKER_START.sh"
echo "[OK] Oder ZIP:       tar -czf '${DEST##*/}.tar.gz' -C '$(dirname "$DEST")' '${DEST##*/}'"
