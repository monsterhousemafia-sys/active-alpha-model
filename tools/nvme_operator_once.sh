#!/usr/bin/env bash
# Einmal PIN/Passwort (grafisch oder sudo) — danach NVMe ohne weitere Freigabe.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
USER_NAME="${USER:-machinax7}"
MOUNT_SCRIPT="$ROOT/tools/mount_nvme_active_alpha.sh"
SUDOERS="/etc/sudoers.d/active-alpha-nvme"

_run_root() {
  local runner="sudo"
  if [[ -n "${DISPLAY:-}" ]] && command -v pkexec >/dev/null 2>&1; then
    runner="pkexec"
  fi
  "$runner" bash -s <<ROOT
set -euo pipefail
command -v ntfs-3g >/dev/null || apt-get install -y ntfs-3g
install -d -m 0750 /etc/sudoers.d
printf '%s\n' "${USER_NAME} ALL=(ALL) NOPASSWD: ${MOUNT_SCRIPT}" >${SUDOERS}
chmod 0440 ${SUDOERS}
visudo -c -f ${SUDOERS}
bash "${MOUNT_SCRIPT}"
ROOT
}

echo "=============================================="
echo " NVMe — einmal PIN/Passwort, danach automatisch"
echo "=============================================="

if "$PY" -c "
from pathlib import Path
from execution.linux_nvme_storage import storage_status
import sys
sys.exit(0 if storage_status(Path('$ROOT')).get('constant_storage_active') else 1)
" 2>/dev/null; then
  echo "[OK] NVMe bereits gemountet — überspringe PIN"
else
  echo " Bitte jetzt einmal PIN oder Passwort bestätigen …"
  _run_root
fi

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
echo " Danach: bash tools/king_ops.sh nvme — ohne PIN"
echo "=============================================="
