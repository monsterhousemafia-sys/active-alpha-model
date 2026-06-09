#!/usr/bin/env bash
# NVMe vollständig: Mount → Migration → Linux-Potenzial-Scan (Operator-Pfad).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

echo "=============================================="
echo " NVMe Operator — $(date +%H:%M:%S)"
echo "=============================================="

mount_nvme() {
  if "$PY" -c "
from pathlib import Path
from execution.linux_nvme_storage import storage_status
import sys
sys.exit(0 if storage_status(Path('$ROOT')).get('constant_storage_active') else 1)
" 2>/dev/null; then
    echo "[OK] NVMe bereits aktiv"
    return 0
  fi
  echo "--- Mount ---"
  if sudo -n bash "$ROOT/tools/mount_nvme_active_alpha.sh" 2>/dev/null; then
    return 0
  fi
  if bash "$ROOT/tools/mount_nvme_active_alpha.sh" 2>/dev/null; then
    return 0
  fi
  echo "[HINWEIS] Einmal PIN — danach automatisch:" >&2
  echo "  bash tools/nvme_operator_once.sh" >&2
  return 1
}

mount_nvme || exit 1

echo "--- Migration ---"
bash "$ROOT/tools/setup_nvme_storage.sh"

echo "--- Linux-Potenzial ---"
"$PY" -c "
from pathlib import Path
from analytics.linux_potential import scan_linux_potential
import json
doc = scan_linux_potential(Path('$ROOT'), persist=True)
print(json.dumps({
    'potential_pct': doc.get('potential_pct'),
    'dimensions_ok': doc.get('dimensions_ok'),
    'dimensions_total': doc.get('dimensions_total'),
    'headline_de': doc.get('headline_de'),
}, ensure_ascii=False, indent=2))
"

echo " Evidence:       evidence/linux_potential_latest.json"
echo "=============================================="
