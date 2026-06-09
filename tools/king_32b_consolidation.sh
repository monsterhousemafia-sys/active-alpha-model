#!/usr/bin/env bash
# König 32B — App-Konsolidierung verifizieren + build-kernel.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
LOG="$ROOT/evidence/king_32b_consolidation.log"
LOCK="$ROOT/evidence/king_32b_consolidation.lock"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[32B-consolidation] warte auf anderen Lauf …" | tee -a "$LOG"
  flock 9
  exit 0
fi

echo "[32B-consolidation] Hub + Desktop-Cache …" | tee -a "$LOG"
"$PY" "$ROOT/tools/preview_hub.py" --ensure >/dev/null 2>&1 || true
"$PY" -c "from pathlib import Path; from analytics.desktop_shell_cache import warm_desktop_cache; warm_desktop_cache(Path('$ROOT'), fast=True, block=True)" >>"$LOG" 2>&1 || true

echo "[32B-consolidation] Audit …" | tee -a "$LOG"
AUDIT_JSON="$("$PY" -c "
from pathlib import Path
from analytics.local_apps_registry import build_local_apps_audit
from analytics.consolidation_32b_registry import build_32b_consolidation_mandate
r = Path('$ROOT')
doc = build_local_apps_audit(r, persist=True, include_runtime=True)
build_32b_consolidation_mandate(r)
print(doc.get('ok_count', 0), doc.get('total', 0), doc.get('all_ok', False))
" 2>>"$LOG")"
read -r OK_N TOTAL ALL_OK <<<"$AUDIT_JSON"
echo "[32B-consolidation] ${OK_N}/${TOTAL} all_ok=${ALL_OK}" | tee -a "$LOG"

bash "$ROOT/tools/setup_r3_desktop_os.sh" >>"$LOG" 2>&1 || true

if [[ "${ALL_OK}" == "True" && "${AA_KING_32B_CONSOLIDATION_VERIFY:-0}" != "1" ]]; then
  echo "[32B-consolidation] Konsolidierung OK — kein build-kernel (VERIFY=1 erzwingt)." | tee -a "$LOG"
  bash "$ROOT/tools/r3_desktop_health.sh" | tee -a "$LOG"
  exit 0
fi

MANDATE="$(cat "$ROOT/evidence/king_32b_consolidation_mandate.txt")"
exec bash "$ROOT/tools/king_32b_build_kernel.sh" "$MANDATE" "$LOG"
