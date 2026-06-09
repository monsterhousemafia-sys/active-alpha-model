#!/usr/bin/env bash
# König 32B — neue einheitliche GUI für alle Oberflächen (build-kernel).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
LOG="$ROOT/evidence/king_32b_gui_rebuild.log"

echo "[32B-GUI] Hub + Desktop-Cache …" | tee -a "$LOG"
"$PY" "$ROOT/tools/preview_hub.py" --ensure >/dev/null 2>&1 || true
"$PY" -c "
from pathlib import Path
from analytics.desktop_shell_cache import warm_desktop_cache
warm_desktop_cache(Path('$ROOT'), fast=True, block=True)
" >>"$LOG" 2>&1 || true

echo "[32B-GUI] Remaster-Gate …" | tee -a "$LOG"
"$PY" -c "
from pathlib import Path
from analytics.gui_remaster_gate import verify_remaster_invariants
doc = verify_remaster_invariants(Path('$ROOT'))
print('[gate]', doc.get('ok_count'), '/', doc.get('total'), 'ok=', doc.get('ok'))
" 2>&1 | tee -a "$LOG"

if pgrep -f "ai_kernel.py build-kernel" >/dev/null 2>&1; then
  echo "[32B-GUI] Hinweis: anderer build-kernel läuft — ggf. warten oder alten Prozess beenden" | tee -a "$LOG"
fi

echo "[32B-GUI] GUI-Audit + Mandat …" | tee -a "$LOG"
AUDIT_JSON="$("$PY" -c "
from pathlib import Path
from analytics.gui_32b_registry import build_gui_32b_audit, build_32b_gui_mandate
r = Path('$ROOT')
doc = build_gui_32b_audit(r, persist=True)
build_32b_gui_mandate(r)
print(doc.get('ok_count', 0), doc.get('total', 0))
" 2>>"$LOG")"
read -r OK_N TOTAL <<<"$AUDIT_JSON"
echo "[32B-GUI] Module: ${OK_N}/${TOTAL}" | tee -a "$LOG"

MANDATE="$(cat "$ROOT/evidence/king_32b_gui_rebuild_mandate.txt")"
echo "[32B-GUI] build-kernel startet (qwen2.5-coder:32b, max 128 Schritte) …" | tee -a "$LOG"
echo "[32B-GUI] Log: evidence/king_32b_gui_rebuild.log · Ergebnis: evidence/r3_build_kernel_latest.json" | tee -a "$LOG"
exec bash "$ROOT/tools/king_32b_build_kernel.sh" "$MANDATE" "$LOG"
