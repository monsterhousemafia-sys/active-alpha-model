#!/usr/bin/env bash
# König 32B — H1-assoziierte Fehler beheben (Evidenz + Code, kein Cursor-H1-Backtest).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
LOG="$ROOT/evidence/king_32b_h1_fix.log"
LOCK="$ROOT/evidence/king_32b_h1_fix.lock"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[32B-H1] anderer Lauf aktiv — warte …" | tee -a "$LOG"
  flock 9
  echo "[32B-H1] Vorheriger Lauf fertig." | tee -a "$LOG"
  exit 0
fi

echo "[32B-H1] Prep-Sync (Governance, keine Benchmark-Autostart bei Seal optional) …" | tee -a "$LOG"
PREP_JSON="$("$PY" -c "
from pathlib import Path
from analytics.h1_32b_registry import prep_h1_evidence_sync, build_32b_h1_mandate, collect_h1_errors
r = Path('$ROOT')
prep_h1_evidence_sync(r)
build_32b_h1_mandate(r)
doc = collect_h1_errors(r)
print(doc.get('error_count', 0), doc.get('ok', False))
" 2>>"$LOG")"
read -r ERR_N ALL_OK <<<"$PREP_JSON"
echo "[32B-H1] Fehler nach Prep: ${ERR_N} · ok=${ALL_OK}" | tee -a "$LOG"

bash "$ROOT/tools/king_ops.sh" status 2>&1 | tee -a "$LOG" || true

if [[ "${ALL_OK}" == "True" && "${AA_KING_32B_H1_VERIFY:-0}" != "1" ]]; then
  echo "[32B-H1] H1-Evidenz konsistent — kein build-kernel (VERIFY=1 erzwingt 32B)." | tee -a "$LOG"
  bash "$ROOT/tools/king_ops.sh" pulse --force 2>&1 | tee -a "$LOG" || true
  exit 0
fi

if pgrep -f "ai_kernel.py build-kernel" >/dev/null 2>&1; then
  echo "[32B-H1] build-kernel läuft — warte auf Abschluss …" | tee -a "$LOG"
  while pgrep -f "ai_kernel.py build-kernel" >/dev/null 2>&1; do
    sleep 5
  done
fi

MANDATE="$(cat "$ROOT/evidence/king_32b_h1_fix_mandate.txt")"
echo "[32B-H1] build-kernel (Warteschlange) …" | tee -a "$LOG"
exec bash "$ROOT/tools/king_32b_build_kernel.sh" "$MANDATE" "$LOG"
