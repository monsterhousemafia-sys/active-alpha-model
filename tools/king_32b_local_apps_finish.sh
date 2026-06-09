#!/usr/bin/env bash
# König 32B — alle Anwendungen prüfen und lauffähig machen.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
LOG="$ROOT/evidence/king_32b_local_apps_finish.log"
LOCK="$ROOT/evidence/king_32b_local_apps_finish.lock"
VERIFY="${AA_KING_32B_APPS_VERIFY:-0}"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[32B-apps] anderer Lauf aktiv — warte auf Abschluss …" | tee -a "$LOG"
  flock 9
  echo "[32B-apps] Vorheriger Lauf fertig — Health-Check …" | tee -a "$LOG"
  "$PY" "$ROOT/tools/preview_hub.py" --ensure >/dev/null 2>&1 || true
  bash "$ROOT/tools/r3_desktop_health.sh" | tee -a "$LOG"
  exit 0
fi

echo "[32B-apps] Hub + Desktop-Cache …" | tee -a "$LOG"
"$PY" "$ROOT/tools/preview_hub.py" --ensure >/dev/null 2>&1 || true
"$PY" -c "
from pathlib import Path
from analytics.desktop_shell_cache import warm_desktop_cache
warm_desktop_cache(Path('$ROOT'), fast=True, block=True)
" >>"$LOG" 2>&1 || true

echo "[32B-apps] Desktop-Einträge …" | tee -a "$LOG"
bash "$ROOT/tools/setup_r3_desktop_os.sh" >>"$LOG" 2>&1 || true

echo "[32B-apps] Audit + Laufzeit …" | tee -a "$LOG"
AUDIT_JSON="$("$PY" -c "
from pathlib import Path
from analytics.local_apps_registry import build_local_apps_audit, build_32b_apps_mandate
r = Path('$ROOT')
doc = build_local_apps_audit(r, persist=True, include_runtime=True)
build_32b_apps_mandate(r)
print(doc.get('ok_count', 0), doc.get('total', 0), doc.get('all_ok', False), doc.get('runtime_ok_count', 0))
" 2>>"$LOG")"
read -r OK_N TOTAL ALL_OK RT_OK <<<"$AUDIT_JSON"
echo "[32B-apps] Datei ${OK_N}/${TOTAL} · Laufzeit ${RT_OK}/${TOTAL} · all_ok=${ALL_OK}" | tee -a "$LOG"

if [[ "${ALL_OK}" == "True" && "${VERIFY}" != "1" ]]; then
  echo "[32B-apps] Alle Apps lauffähig — kein build-kernel (VERIFY=1 erzwingt 32B)." | tee -a "$LOG"
  bash "$ROOT/tools/r3_desktop_health.sh" | tee -a "$LOG"
  exit 0
fi

if pgrep -f "ai_kernel.py build-kernel" >/dev/null 2>&1; then
  echo "[32B-apps] build-kernel läuft bereits — warte auf Abschluss …" | tee -a "$LOG"
  while pgrep -f "ai_kernel.py build-kernel" >/dev/null 2>&1; do
    sleep 5
  done
  echo "[32B-apps] build-kernel fertig — Hub + Health …" | tee -a "$LOG"
  "$PY" "$ROOT/tools/preview_hub.py" --ensure >/dev/null 2>&1 || true
  bash "$ROOT/tools/r3_desktop_health.sh" | tee -a "$LOG"
  exit 0
fi

MANDATE="$(cat "$ROOT/evidence/king_32b_local_apps_mandate.txt")"
echo "[32B-apps] build-kernel (Warteschlange) …" | tee -a "$LOG"
exec bash "$ROOT/tools/king_32b_build_kernel.sh" "$MANDATE" "$LOG"
