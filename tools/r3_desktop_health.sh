#!/usr/bin/env bash
# Stack-Integrität — Hub + R3 getrennt, fail-closed Exit-Code.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init
ROOT="$R3_ROOT"
PY="$R3_PY"

echo "=============================================="
echo " Stack-Integrität — $(date +%H:%M:%S)"
echo "=============================================="

if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
  echo " Display:        ja (${DISPLAY:-}${WAYLAND_DISPLAY:+/Wayland})"
else
  echo " Display:        NEIN — Qt-Cockpit nicht startbar"
fi

EXIT=0
"$PY" -c "
from pathlib import Path
from analytics.stack_integrity import build_integrity_report, persist_integrity_report
import sys

root = Path('$ROOT')
doc = build_integrity_report(root)
persist_integrity_report(root, doc)
hub = doc.get('hub') or {}
r3 = doc.get('r3') or {}

print('--- Hub (HTTP) ---')
print(' Hub :' + str(doc.get('port')) + ':     ' + ('ONLINE' if hub.get('online') else 'OFFLINE'))
print(' /login:         ' + ('OK' if hub.get('route_login_ok') else 'FEHLER'))
print('--- R3 (Oberfläche) ---')
print(' Mirror-API:     ' + ('OK' if r3.get('mirror_api_ok') else 'FEHLER'))
print(' Mirror-State:   ' + ('OK' if r3.get('mirror_state_ok') else 'FEHLER'))
print(' Surface /r3:    ' + ('OK' if r3.get('surface_page_ok') else 'LANGSAM'))
print(' Cockpit (Qt):   ' + ('LAUFEND' if r3.get('cockpit_running') else 'GESTOPPT'))
mode = 'Desktop (6/6 kritisch)' if doc.get('desktop_session') else 'Headless (4/6 kritisch)'
print(' Modus:          ' + mode)
print(' STACK:          ' + ('OK' if doc.get('stack_ok') else 'FEHLER'))
for f in doc.get('failures_de') or []:
    print(' Fehler:         ' + str(f)[:70])
for w in doc.get('warnings_de') or []:
    print(' Warnung:        ' + str(w)[:70])
sys.exit(0 if doc.get('stack_ok') else 1)
" || EXIT=1

if "$PY" -c "import PySide6" 2>/dev/null; then echo " PySide6:        OK"; else echo " PySide6:        FEHLT"; EXIT=1; fi
if "$PY" -c "from PySide6.QtWebEngineWidgets import QWebEngineView" 2>/dev/null; then echo " WebEngine:      OK"; else echo " WebEngine:      FEHLT"; EXIT=1; fi

if [[ -x "$HOME/.local/bin/r3" || -L "$HOME/.local/bin/r3" ]]; then
  echo " Befehl r3:      installiert"
else
  echo " Befehl r3:      fehlt (bash tools/install_r3_app.sh)"
fi

if [[ -f "$HOME/.config/autostart/r3-os-session.desktop" ]]; then
  echo " Login-Autostart: aktiv"
else
  echo " Login-Autostart: fehlt (bash tools/install_r3_app.sh)"
fi

echo "----------------------------------------------"
r3_print_upgrade_hint
echo " Abgleich:       bash tools/r3_sync.sh"
echo " Integrität:     bash tools/stack_integrity.sh --repair"
echo " Hub:            bash tools/hub_ensure.sh"
echo " R3 Cockpit:     bash tools/r3_cockpit.sh"
echo " Evidence:       evidence/stack_integrity_latest.json"
echo "=============================================="
exit "$EXIT"
