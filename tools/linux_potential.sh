#!/usr/bin/env bash
# Linux-Potenzial — Scan + sichere Anwendung (ohne sudo).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help)
      cat <<'EOF'
linux_potential.sh — Linux-Umgebung für R3 voll nutzen

  (ohne Flags)   Scan — Dimensionen + nächster Hebel
  --apply        Sichere Schritte: local-first, NVMe-env, Hub, R3-Align

NVMe mount (sudo): AA_OPERATOR_APPROVE_D=1 bash tools/linux_operator_system.sh nvme
EOF
      exit 0
      ;;
  esac
done

echo "=============================================="
echo " Linux-Potenzial — $(date +%H:%M:%S)"
echo "=============================================="

if [[ "$APPLY" -eq 1 ]]; then
  echo "--- Apply (sicher, ohne sudo) ---"
  "$R3_PY" -c "
from pathlib import Path
from analytics.linux_potential import apply_linux_potential_safe
import json
doc = apply_linux_potential_safe(Path('$R3_ROOT'))
print(json.dumps({'ok': doc.get('ok'), 'headline_de': doc.get('headline_de'), 'next_de': doc.get('next_de'), 'steps': len(doc.get('steps') or [])}, ensure_ascii=False, indent=2))
" || exit 1
  bash "$R3_ROOT/tools/r3_sync.sh" 2>&1 | tail -8
else
  "$R3_PY" -c "
from pathlib import Path
from analytics.linux_potential import scan_linux_potential
import json
doc = scan_linux_potential(Path('$R3_ROOT'), persist=True)
for d in doc.get('dimensions') or []:
    mark = 'OK' if d.get('ok') else 'OFFEN'
    print(f\" {mark:5} {d.get('label_de')}: {d.get('detail_de')}\")
print('----------------------------------------------')
print(' ' + str(doc.get('headline_de')))
print(' Nächster Hebel: ' + str(doc.get('next_de')))
"
fi

echo "----------------------------------------------"
echo " Apply:          bash tools/king_ops.sh linux-potential --apply"
echo " NVMe:           bash tools/king_ops.sh nvme"
echo " Evidence:       evidence/linux_potential_latest.json"
echo "=============================================="
