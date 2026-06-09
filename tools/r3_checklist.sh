#!/usr/bin/env bash
# R3 Betriebs-Checkliste — maschinenlesbarer Scan.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

REPAIR=0
for arg in "$@"; do
  case "$arg" in
    --repair) REPAIR=1 ;;
    -h|--help)
      cat <<'EOF'
r3_checklist.sh — R3 Betriebs-Checkliste (A–G)

  (ohne Flags)   Scan aller Punkte → evidence/r3_operational_checklist_latest.json
  --repair       series-ready --repair + erneuter Scan

Beispiele:
  bash tools/king_ops.sh r3-checklist
  bash tools/king_ops.sh r3-checklist --repair
EOF
      exit 0
      ;;
  esac
done

echo "=============================================="
echo " R3 Checkliste — $(date +%H:%M:%S)"
echo "=============================================="

if [[ "$REPAIR" -eq 1 ]]; then
  bash "$R3_ROOT/tools/series_readiness.sh" --repair || true
fi

"$R3_PY" -c "
from pathlib import Path
from analytics.r3_operational_checklist import scan_operational_checklist
import json
doc = scan_operational_checklist(Path('$R3_ROOT'), persist=True)
for sec in doc.get('sections') or []:
    for it in sec.get('items') or []:
        st = str(it.get('status') or ('OK' if it.get('ok') else 'FAIL'))
        print(f\" {st:7} [{sec.get('id')}] {it.get('id')}: {it.get('detail_de')}\")
print('----------------------------------------------')
print(' ' + str(doc.get('headline_de')))
print(json.dumps({
    'checklist_ok': doc.get('checklist_ok'),
    'items_ok': doc.get('items_ok'),
    'items_total': doc.get('items_total'),
}, ensure_ascii=False))
" || exit 1

OK="$("$R3_PY" -c "
import json
from pathlib import Path
doc = json.loads((Path('$R3_ROOT') / 'evidence/r3_operational_checklist_latest.json').read_text(encoding='utf-8'))
print('1' if doc.get('checklist_ok') else '0')
")"

echo "----------------------------------------------"
echo " Evidence:       evidence/r3_operational_checklist_latest.json"
if [[ "$OK" == "1" ]]; then
  echo " Status:         CHECKLISTE OK"
else
  echo " Status:         BLOCKER — --repair oder Einzelpunkt beheben"
fi
echo "=============================================="
[[ "$OK" == "1" ]] || exit 1
