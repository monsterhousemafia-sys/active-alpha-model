#!/usr/bin/env bash
# Serienreife — lokales R3-Produkt (fail-closed Gate).
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
series_readiness.sh — Serienreife lokales R3

  (ohne Flags)   Scan — kritische Gates + Warnungen
  --repair       Hub + R3-Align + Stack-Reparatur + erneuter Scan

Beispiele:
  bash tools/king_ops.sh series-ready
  bash tools/king_ops.sh series-ready --repair
EOF
      exit 0
      ;;
  esac
done

echo "=============================================="
echo " Serienreife — $(date +%H:%M:%S)"
echo "=============================================="

echo "--- Hub ---"
if ! "$R3_PY" -c "
from analytics.hub_runtime import DEFAULT_PORT, is_healthy
import sys
sys.exit(0 if is_healthy(DEFAULT_PORT) else 1)
" 2>/dev/null; then
  bash "$R3_ROOT/tools/hub_ensure.sh" >/dev/null 2>&1 || true
fi

if [[ "$REPAIR" -eq 1 ]]; then
  echo "--- Repair (sicher) ---"
  "$R3_PY" -c "
from pathlib import Path
from analytics.series_readiness import apply_series_readiness_repair
import json
doc = apply_series_readiness_repair(Path('$R3_ROOT'))
print(json.dumps({
    'ok': doc.get('ok'),
    'series_ready': doc.get('series_ready'),
    'readiness_pct': doc.get('readiness_pct'),
    'headline_de': doc.get('headline_de'),
}, ensure_ascii=False, indent=2))
" || exit 1
fi

"$R3_PY" -c "
from pathlib import Path
from analytics.series_readiness import scan_series_readiness
import json
doc = scan_series_readiness(Path('$R3_ROOT'), persist=True, force=True, fast=True)
for g in doc.get('gates') or []:
    tier = str(g.get('tier') or 'critical')
    mark = 'OK' if g.get('ok') else ('WARN' if tier == 'warn' else 'FAIL')
    print(f\" {mark:4} {g.get('label_de')}: {g.get('detail_de')}\")
print('----------------------------------------------')
print(' ' + str(doc.get('headline_de')))
print(' Nächster Schritt: ' + str(doc.get('next_de')))
print(json.dumps({'series_ready': doc.get('series_ready'), 'readiness_pct': doc.get('readiness_pct')}, ensure_ascii=False))
" || exit 1

READY="$("$R3_PY" -c "
import json
from pathlib import Path
doc = json.loads((Path('$R3_ROOT') / 'evidence/series_readiness_latest.json').read_text(encoding='utf-8'))
print('1' if doc.get('series_ready') else '0')
")"

echo "----------------------------------------------"
echo "--- Checkliste ---"
"$R3_PY" -c "
from pathlib import Path
from analytics.r3_operational_checklist import scan_operational_checklist
doc = scan_operational_checklist(Path('$R3_ROOT'), persist=True)
print(' ' + str(doc.get('headline_de')))
" 2>/dev/null || true

echo " Evidence:       evidence/series_readiness_latest.json"
echo " Checkliste:     evidence/r3_operational_checklist_latest.json"
echo " Oberfläche:     $(r3_hub_base_url)$(r3_surface_path)"
if [[ "$READY" == "1" ]]; then
  echo " Status:         SERIENREIF (lokal)"
else
  echo " Status:         NOCH NICHT SERIENREIF — --repair oder Blocker beheben"
fi
echo "=============================================="
[[ "$READY" == "1" ]] || exit 1
