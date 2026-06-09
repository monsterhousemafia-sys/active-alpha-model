#!/usr/bin/env bash
# R3 Abgleich — Hub, Laufzeitprofil, Upgrade-Scan, Cache, Stack (ein Pfad).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

REPAIR=0
LAUNCH=0
FLOW=0
for arg in "$@"; do
  case "$arg" in
    --repair) REPAIR=1 ;;
    --launch) LAUNCH=1; REPAIR=1 ;;
    --flow) FLOW=1 ;;
    -h|--help)
      cat <<'EOF'
r3_sync.sh — R3 fein aufeinander abstimmen

  (ohne Flags)     Hub + Align + Stack prüfen
  --repair         Bei Fehler: Stack reparieren (Hub, Mirror, Cache)
  --launch         Wie --repair + Qt-Cockpit starten (Display nötig)
  --flow           Zusätzlich R3-Fluss-Orchestrator (Fluidität)

Beispiele:
  bash tools/r3_sync.sh
  bash tools/r3_sync.sh --repair
  bash tools/r3_sync.sh --launch --flow
  bash tools/king_ops.sh r3-sync --repair
EOF
      exit 0
      ;;
  esac
done

export R3_SESSION=1
export R3_NATIVE_SHELL=1

echo "=============================================="
echo " R3 Abgleich — $(date +%H:%M:%S)"
echo "=============================================="
echo " Projekt:        $R3_ROOT"
echo " Oberfläche:     $(r3_hub_base_url)$(r3_surface_path)"

EXIT=0

echo "--- Hub ---"
if ! "$R3_PY" -c "
from pathlib import Path
from analytics.hub_runtime import DEFAULT_PORT, is_healthy
import sys
sys.exit(0 if is_healthy(DEFAULT_PORT) else 1)
" 2>/dev/null; then
  bash "$R3_ROOT/tools/hub_ensure.sh" >/dev/null 2>&1 || true
fi
if "$R3_PY" -c "
from pathlib import Path
from analytics.hub_runtime import DEFAULT_PORT, build_health_report
import sys
rep = build_health_report(Path('$R3_ROOT'), port=DEFAULT_PORT)
print(' Hub :' + str(rep.get('port')) + ':     ' + ('ONLINE' if rep.get('online') else 'OFFLINE'))
sys.exit(0 if rep.get('online') else 1)
"; then
  :
else
  EXIT=1
fi

FLOW_FLAG=0
[[ "$FLOW" -eq 1 ]] && FLOW_FLAG=1

echo "--- Align (Profil · Upgrade · Cache) ---"
"$R3_PY" -c "
from pathlib import Path
import json, sys
from analytics.r3_runtime_upgrade import align_r3_surface

root = Path('$R3_ROOT')
doc = align_r3_surface(
    root,
    scan_upgrades=True,
    warm_cache=True,
    sync_flow=bool(int('$FLOW_FLAG')),
    persist=True,
)
print(' Profil:         ' + str(doc.get('runtime_profile_label_de') or doc.get('runtime_profile_id')))
print(' Cache:          ' + ('OK' if any(s.get('step') == 'warm_cache' and s.get('ok') for s in doc.get('steps') or []) else '—'))
if doc.get('upgrade_pending'):
    pend = doc.get('pending') or {}
    print(' Update:         BEREIT — ' + str(pend.get('label_de') or 'R3-Update'))
    for line in pend.get('changes_de') or []:
        print('   · ' + str(line)[:72])
    print(' Aktion:         In R3 bestätigen (Übernehmen / Später)')
else:
    print(' Update:         kein offener Vorschlag')
print(' ' + str(doc.get('confirmation_de') or ''))
if not doc.get('ok'):
    sys.exit(1)
" || EXIT=1

echo "--- Stack ---"
STACK_ARGS=()
[[ "$REPAIR" -eq 1 ]] && STACK_ARGS+=(--repair)
[[ "$LAUNCH" -eq 1 ]] && STACK_ARGS+=(--launch)

if bash "$R3_ROOT/tools/stack_integrity.sh" "${STACK_ARGS[@]}" 2>/dev/null | "$R3_PY" -c "
import json, sys
doc = json.load(sys.stdin)
print(' STACK:          ' + ('OK' if doc.get('stack_ok') else 'FEHLER'))
for f in doc.get('failures_de') or []:
    print(' Fehler:         ' + str(f)[:70])
for w in doc.get('warnings_de') or []:
    print(' Warnung:        ' + str(w)[:70])
sys.exit(0 if doc.get('stack_ok') else 1)
"; then
  :
else
  EXIT=1
fi

if [[ "$REPAIR" -eq 1 ]]; then
  echo "--- Prognose (Live-Cash → Plan) ---"
  bash "$R3_ROOT/tools/king_ops.sh" prognosis run 2>/dev/null | head -4 || echo " Prognose: ausstehend (T212 Trust)"
fi

echo "----------------------------------------------"
r3_print_growth_hint
r3_print_series_hint
r3_print_upgrade_hint
echo " Start Cockpit:  bash tools/r3_cockpit.sh"
echo " Voll-Pipeline:  bash tools/king_ops.sh r3-sync --flow"
echo " Evidence:       evidence/r3_runtime_upgrade_latest.json"
echo "=============================================="
exit "$EXIT"
