#!/usr/bin/env bash
# Umfassendes Systemaudit — Safety, R3, Serienreife, Linux.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

LIVE=0
TESTS=0
for arg in "$@"; do
  case "$arg" in
    --live) LIVE=1 ;;
    --tests) TESTS=1 ;;
    -h|--help)
      cat <<'EOF'
system_audit.sh — Umfassendes Systemaudit

  (ohne Flags)   Audit aus Evidence + frische Scans (Serienreife, Growth)
  --live         Stack zusätzlich live prüfen (HTTP)
  --tests        Kern-pytest-Suite ausführen (~2 Min)

Beispiele:
  bash tools/king_ops.sh system-audit
  bash tools/king_ops.sh system-audit --tests
EOF
      exit 0
      ;;
  esac
done

echo "=============================================="
echo " Systemaudit — $(date +%H:%M:%S)"
echo "=============================================="

if ! "$R3_PY" -c "
from analytics.hub_runtime import DEFAULT_PORT, is_healthy
import sys
sys.exit(0 if is_healthy(DEFAULT_PORT) else 1)
" 2>/dev/null; then
  bash "$R3_ROOT/tools/hub_ensure.sh" >/dev/null 2>&1 || true
fi

"$R3_PY" -c "
from pathlib import Path
from analytics.system_audit import run_system_audit
import json
doc = run_system_audit(
    Path('$R3_ROOT'),
    persist=True,
    live_stack=bool(int('$LIVE')),
    run_tests=bool(int('$TESTS')),
)
for s in doc.get('sections') or []:
    tier = str(s.get('tier') or 'critical')
    mark = 'OK' if s.get('ok') else ('WARN' if tier in ('warn', 'info') else 'FAIL')
    if tier == 'info':
        mark = 'INFO'
    print(f\" {mark:4} {s.get('label_de')}: {s.get('detail_de')}\")
print('----------------------------------------------')
print(' ' + str(doc.get('headline_de')))
print(' Nächster Schritt: ' + str(doc.get('next_de')))
print(json.dumps({'audit_ok': doc.get('audit_ok'), 'critical_ok': doc.get('critical_ok'), 'critical_total': doc.get('critical_total')}, ensure_ascii=False))
" || exit 1

OK="$("$R3_PY" -c "
import json
from pathlib import Path
doc = json.loads((Path('$R3_ROOT') / 'evidence/system_audit_latest.json').read_text(encoding='utf-8'))
print('1' if doc.get('audit_ok') else '0')
")"

echo "----------------------------------------------"
echo " Evidence:       evidence/system_audit_latest.json"
if [[ "$OK" == "1" ]]; then
  echo " Status:         AUDIT PASS"
else
  echo " Status:         AUDIT FAIL — series-ready --repair"
fi
echo "=============================================="
[[ "$OK" == "1" ]] || exit 1
