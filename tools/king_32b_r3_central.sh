#!/usr/bin/env bash
# König 32B — R3 als zentrale Quelle fertigbauen.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
LOG="$ROOT/evidence/king_32b_r3_central.log"
LOCK="$ROOT/evidence/king_32b_r3_central.lock"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[32B-R3] warte auf anderen Lauf …" | tee -a "$LOG"
  flock 9
  exit 0
fi

echo "[32B-R3] Hub + Desktop-Cache …" | tee -a "$LOG"
"$PY" "$ROOT/tools/preview_hub.py" --ensure >/dev/null 2>&1 || true
"$PY" -c "from pathlib import Path; from analytics.desktop_shell_cache import warm_desktop_cache; warm_desktop_cache(Path('$ROOT'), fast=True, block=True)" >>"$LOG" 2>&1 || true

echo "[32B-R3] Zentral-Status …" | tee -a "$LOG"
STAT_JSON="$("$PY" -c "
from pathlib import Path
from analytics.r3_central_registry import build_32b_r3_central_mandate, build_r3_central_status
r = Path('$ROOT')
build_r3_central_status(r, persist=True)
build_32b_r3_central_mandate(r)
doc = build_r3_central_status(r, persist=False)
print(doc.get('feeds_ok', 0), doc.get('feeds_total', 0), doc.get('all_ok', False))
" 2>>"$LOG")"
read -r OK_N TOTAL ALL_OK <<<"$STAT_JSON"
echo "[32B-R3] Feeds ${OK_N}/${TOTAL} all_ok=${ALL_OK}" | tee -a "$LOG"

if [[ "${ALL_OK}" == "True" && "${AA_KING_32B_R3_CENTRAL_VERIFY:-0}" != "1" ]]; then
  echo "[32B-R3] Zentrale OK — kein build-kernel (VERIFY=1 erzwingt 32B)." | tee -a "$LOG"
  bash "$ROOT/tools/r3_desktop_health.sh" | tee -a "$LOG"
  exit 0
fi

MANDATE="$(cat "$ROOT/evidence/king_32b_r3_central_mandate.txt")"
exec bash "$ROOT/tools/king_32b_build_kernel.sh" "$MANDATE" "$LOG"
