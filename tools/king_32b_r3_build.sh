#!/usr/bin/env bash
# König 32B — R3 Lokal-Bau effizient (Mandat → build-kernel → r3_sync).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1

TOPIC="${1:-}"
LOG="${ROOT}/evidence/king_32b_r3_build.log"
mkdir -p "$(dirname "$LOG")"

echo "[32B-R3-Bau] Mandat erzeugen …" | tee -a "$LOG"
MANDATE="$("$PY" -c "
from pathlib import Path
from analytics.r3_build_mandate import build_r3_local_mandate, notify_king_build_handoff
root = Path('$ROOT')
topic = '$TOPIC'.strip()
doc = build_r3_local_mandate(root, topic=topic)
notify_king_build_handoff(root, doc)
print(doc.get('mandate_de') or '')
" 2>>"$LOG")"

if [[ -z "$MANDATE" ]]; then
  echo "[32B-R3-Bau] FEHLER — leeres Mandat" | tee -a "$LOG"
  exit 2
fi

echo "[32B-R3-Bau] build-kernel (Coder-32B) …" | tee -a "$LOG"
if ! bash "$ROOT/tools/king_32b_build_kernel.sh" "$MANDATE" "$LOG"; then
  echo "[32B-R3-Bau] build-kernel Exit ≠ 0" | tee -a "$LOG"
  exit 1
fi

echo "[32B-R3-Bau] Abgleich r3_sync …" | tee -a "$LOG"
bash "$ROOT/tools/r3_sync.sh" --repair 2>&1 | tee -a "$LOG" || true

echo "[32B-R3-Bau] fertig — Operator: http://127.0.0.1:17890/r3 (Update bestätigen)" | tee -a "$LOG"
