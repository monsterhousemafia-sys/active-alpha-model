#!/usr/bin/env bash
# König: kleines Universal-Paket (Win/Mac/Linux, ~100 KB) — kinderleicht.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"

DEST_ARG="${1:-}"
if [[ -z "$DEST_ARG" ]]; then
  DEST_ARG="$(dirname "$ROOT")/active_alpha_worker_LITE"
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
  echo "[FEHLER] Ungültiges Lite-Export-Ziel: ${DEST_ARG}" >&2
  exit 1
fi
mkdir -p "$DEST"

echo "[lite] Hub + Token …"
"$PY" "$ROOT/tools/preview_hub.py" --ensure 2>/dev/null || true
CFG="$("$PY" -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT')
from analytics.preview_federation import prepare_worker_bundle_config
from tools.preview_hub import ensure_hub_running
r = Path('$ROOT')
ensure_hub_running(r, restart=False)
print(json.dumps(prepare_worker_bundle_config(r), ensure_ascii=False))
")"
HUB="$(echo "$CFG" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("hub_join_url") or "")')"

echo "$CFG" > "$DEST/preview_worker_join.json"
cp "$ROOT/tools/universal_preview_worker.py" "$DEST/worker.py"
chmod +x "$DEST/worker.py" 2>/dev/null || true

# Windows — Doppelklick
cat > "$DEST/Windows_START.bat" <<'BAT'
@echo off
cd /d "%~dp0"
title Active Alpha Worker
echo Active Alpha — Rechenleistung beitreten ...
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py -3
if not defined PY (
  echo Python 3 fehlt. Installiere von https://www.python.org/downloads/
  echo Haken setzen: "Add Python to PATH"
  pause
  exit / 1
)
%PY% worker.py
if errorlevel 1 pause
BAT

# macOS — Doppelklick (Rechtsklick: Öffnen falls Gatekeeper)
cat > "$DEST/Mac_START.command" <<'MAC'
#!/bin/bash
cd "$(dirname "$0")"
echo "Active Alpha — Rechenleistung beitreten ..."
if command -v python3 >/dev/null; then
  exec python3 worker.py
fi
echo "Python 3 fehlt — brew install python3 oder python.org"
read -r -p "Enter ..."
MAC
chmod +x "$DEST/Mac_START.command"

# Linux
cat > "$DEST/Linux_START.sh" <<'LIN'
#!/bin/bash
cd "$(dirname "$0")"
echo "Active Alpha — Rechenleistung beitreten ..."
exec python3 worker.py
LIN
chmod +x "$DEST/Linux_START.sh"

cat > "$DEST/START_HIER.md" <<EOF
# Active Alpha — In 1 Schritt beitreten

Du spendest **CPU-Leistung** — kein Geld, kein Broker.

## Start (wähle dein System)

| System | Aktion |
|--------|--------|
| **Windows** | Doppelklick auf \`Windows_START.bat\` |
| **macOS** | Doppelklick auf \`Mac_START.command\` |
| **Linux** | Doppelklick oder: \`./Linux_START.sh\` |

Falls Python fehlt: [python.org/downloads](https://www.python.org/downloads/) (Windows: „Add to PATH“ ankreuzen)

## Command Center

$HUB/

## Stoppen

Fenster schließen oder Strg+C. Fertig.

## Probleme?

Vom Worker-PC testen: \`curl $HUB/api/health\`  
**Anderes Netz?** König muss \`ai_kernel spread-remote\` ausführen (HTTPS-URL in ZIP).  
Details: docs/REMOTE_WORKER_DE.md
EOF

TAR="$(dirname "$DEST")/$(basename "$DEST").zip"
rm -f "$TAR"
(cd "$(dirname "$DEST")" && zip -qr "$(basename "$TAR")" "$(basename "$DEST")")

"$PY" -c "
import json
from datetime import datetime, timezone
from pathlib import Path
marker = {
    'lite_dest': '$DEST',
    'lite_zip': '$TAR',
    'join_url': '$HUB/',
    'updated_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
}
p = Path('$ROOT/evidence/community_spread_export.json')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(marker, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
"

echo ""
echo "[OK] Lite-Bundle:  $DEST"
echo "[OK] ZIP (versenden): $TAR"
echo "[OK] Hub: $HUB"
du -sh "$DEST" "$TAR"
