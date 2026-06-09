#!/usr/bin/env bash
# H1-Seal-Pipeline — ein Job: Benchmark → Evaluate → Seal (fail-closed).
# Usage:
#   bash tools/king_h1_seal.sh           # vollständige Pipeline
#   bash tools/king_h1_seal.sh --wait    # nur warten wenn Benchmark läuft
#   bash tools/king_h1_seal.sh --check-only  # Exit 0=sealed, 1=offen, 2=generating
set -euo pipefail
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_init

MODE="${1:-run}"
case "$MODE" in
  --check-only|check) MODE=check ;;
  --wait|wait) MODE=wait ;;
  run|"") MODE=run ;;
  *)
    echo "Usage: $0 [--check-only|--wait]" >&2
    exit 2
    ;;
esac

echo "[king-h1] Pipeline ($MODE)"

SEAL_REQUIRED=1
if "$KING_PY" -c "from pathlib import Path; from analytics.h1_seal_policy import is_h1_seal_required; raise SystemExit(0 if is_h1_seal_required(Path('$KING_ROOT')) else 1)" 2>/dev/null; then
  SEAL_REQUIRED=1
else
  SEAL_REQUIRED=0
  echo "[king-h1] Seal optional (control/h1_seal_policy.json) — kein mom_1-Benchmark nötig"
fi

_king_h1_sync() {
  king_sync_network python 2>/dev/null || true
}

if [[ "$SEAL_REQUIRED" -eq 0 ]]; then
  H1_ST="$(king_h1_status)"
  if [[ "$H1_ST" == "COMPLETE" ]]; then
    echo "[king-h1] H1 COMPLETE — Seal nicht erforderlich"
    [[ "$MODE" == "check" ]] && exit 0
    _king_h1_sync
    exit 0
  fi
fi

if king_h1_sealed; then
  echo "[king-h1] Bereits SEALED"
  [[ "$MODE" == "check" ]] && exit 0
  king_run h1-watch >/dev/null
  _king_h1_sync
  exit 0
fi

if king_csv_ready; then
  echo "[king-h1] CSV da — h1-watch"
  [[ "$MODE" == "check" ]] && exit 1
  king_with_lock h1_seal king_run h1-watch
  _king_h1_sync
  exit $?
fi

if king_benchmark_running; then
  if [[ "$MODE" == "check" ]]; then
    echo "[king-h1] Benchmark läuft (PID $(king_benchmark_pid))"
    exit 2
  fi
  echo "[king-h1] Benchmark läuft — warte (PID $(king_benchmark_pid))"
  if king_wait_benchmark; then
    king_with_lock h1_seal king_run h1-watch
    _king_h1_sync
    exit $?
  fi
  if [[ "$MODE" == "wait" ]]; then
    echo "[king-h1] Benchmark beendet ohne CSV" >&2
    exit 1
  fi
  echo "[king-h1] Benchmark ohne CSV beendet — Neustart" >&2
fi

[[ "$MODE" == "check" ]] && exit 1
[[ "$MODE" == "wait" ]] && { echo "[king-h1] Kein Benchmark aktiv" >&2; exit 1; }

if [[ "$SEAL_REQUIRED" -eq 0 ]]; then
  echo "[king-h1] Benchmark übersprungen — Seal-Policy optional"
  _king_h1_sync
  exit 0
fi

if king_benchmark_running; then
  echo "[king-h1] Benchmark bereits aktiv — kein Zweitstart (PID $(king_benchmark_pid))" >&2
  exit 3
fi

echo "[king-h1] Hard/Soft-Netzwerk-Prep …"
export AA_H1_UNLOAD_OLLAMA="${AA_H1_UNLOAD_OLLAMA:-1}"
export AA_H1_GPU_RETURNS="${AA_H1_GPU_RETURNS:-1}"
bash "$KING_ROOT/tools/king_h1_prep.sh" 2>/dev/null | tail -12 || true

echo "[king-h1] Start Benchmark (flock) …"
king_with_lock h1_benchmark bash -c "
  set -euo pipefail
  cd '$KING_ROOT'
  export AA_H1_UNLOAD_OLLAMA=\${AA_H1_UNLOAD_OLLAMA:-1}
  export AA_H1_GPU_RETURNS=\${AA_H1_GPU_RETURNS:-1}
  '$KING_PY' -u tools/generate_h1_naive_benchmark.py --wait
"

if king_csv_ready; then
  echo "[king-h1] CSV nach Benchmark — h1-watch"
  king_with_lock h1_seal king_run h1-watch
  _king_h1_sync
  exit $?
fi

echo "[king-h1] FEHLER — CSV fehlt nach Benchmark" >&2
exit 1
