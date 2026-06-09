#!/usr/bin/env bash
# Decision Cockpit Update — R3-Web ↔ EXE-Vision (Snapshot + König-Remaster).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

START_GUI=0
for arg in "$@"; do
  case "$arg" in
    --gui-rebuild) START_GUI=1 ;;
    -h|--help)
      cat <<'EOF'
decision_cockpit_update.sh — R3-Web an Decision-Cockpit-Vision anbinden

  (ohne Flags)       Serienreife repair + Snapshot + König-Bridge + Pulse
  --gui-rebuild      Zusätzlich gui-rebuild im Hintergrund (32B)

Beispiele:
  bash tools/king_ops.sh cockpit-update
  bash tools/king_ops.sh cockpit-update --gui-rebuild
EOF
      exit 0
      ;;
  esac
done

echo "=============================================="
echo " Decision Cockpit Update — $(date +%H:%M:%S)"
echo "=============================================="

"$R3_PY" -c "
from pathlib import Path
from analytics.decision_cockpit_update import kickoff_decision_cockpit_update
import json
doc = kickoff_decision_cockpit_update(Path('$R3_ROOT'), persist=True)
print(json.dumps({
    'ok': doc.get('ok'),
    'series_ready': doc.get('series_ready'),
    'readiness_pct': doc.get('readiness_pct'),
    'headline_de': doc.get('headline_de'),
    'next_de': doc.get('next_de'),
}, ensure_ascii=False, indent=2))
for s in doc.get('steps') or []:
    mark = 'OK' if s.get('ok') else 'FAIL'
    print(f\" {mark:4} {s.get('label_de')}\")
" || exit 1

if [[ "$START_GUI" -eq 1 ]]; then
  if pgrep -f "ai_kernel.py build-kernel" >/dev/null 2>&1; then
    echo "--- gui-rebuild: build-kernel läuft bereits"
  else
    echo "--- gui-rebuild im Hintergrund …"
    nohup bash "$R3_ROOT/tools/king_32b_gui_rebuild.sh" >>"$R3_ROOT/evidence/king_32b_gui_rebuild.log" 2>&1 &
    echo " PID $! — Log: evidence/king_32b_gui_rebuild.log"
  fi
fi

UPDATE_OK="$("$R3_PY" -c "
import json
from pathlib import Path
doc = json.loads((Path('$R3_ROOT') / 'evidence/decision_cockpit_update_latest.json').read_text(encoding='utf-8'))
print('1' if doc.get('ok') else '0')
")"

echo "----------------------------------------------"
echo " Evidence:       evidence/decision_cockpit_update_latest.json"
echo " Lessons:        evidence/decision_cockpit_update_lessons_latest.json"
echo " Checkliste:     evidence/r3_operational_checklist_latest.json"
echo " Snapshot:       control/review_snapshot/v5r_decision_cockpit_snapshot.json"
echo " Bridge-Policy:  control/decision_cockpit_r3_bridge.json"
if [[ "$UPDATE_OK" == "1" ]]; then
  echo " Status:         UPDATE OK"
else
  echo " Status:         BLOCKER — bash tools/king_ops.sh cockpit-update (nach Repair)"
fi
echo " Nächster Schritt: bash tools/king_ops.sh gui-rebuild"
echo "=============================================="
[[ "$UPDATE_OK" == "1" ]] || exit 1
