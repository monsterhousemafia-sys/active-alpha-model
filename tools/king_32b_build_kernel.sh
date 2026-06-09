#!/usr/bin/env bash
# Gemeinsame build-kernel-Warteschlange (32B) — ein Lauf zur Zeit.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
MANDATE="${1:-}"
LOG="${2:-$ROOT/evidence/king_32b_build_kernel.log}"
LOCK="$ROOT/evidence/king_32b_build_kernel.lock"

if [[ -z "$MANDATE" ]]; then
  echo "Usage: king_32b_build_kernel.sh <mandate_text|@file> [log]" >&2
  exit 2
fi
if [[ "$MANDATE" == @* ]]; then
  MANDATE="$(cat "${MANDATE#@}")"
fi

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[32B-kernel] anderer build-kernel — warte …" | tee -a "$LOG"
  flock 9
  echo "[32B-kernel] vorheriger Lauf fertig." | tee -a "$LOG"
  exit 0
fi

echo "[32B-kernel] start (qwen2.5-coder:32b) …" | tee -a "$LOG"
exec "$PY" "$ROOT/tools/ai_kernel.py" build-kernel --utterance "$MANDATE" 2>&1 | tee -a "$LOG"
