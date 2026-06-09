#!/usr/bin/env bash
# Legacy-Benchmark prüfen und fail-closed beenden (über ETA, kein CSV, kein echter Progress).
# Usage: bash tools/king_retire_legacy_benchmark.sh [--dry-run]
set -euo pipefail
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_assert_project_root

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

SEAL_POLICY_OFF=0
if ! "$KING_PY" -c "from pathlib import Path; from analytics.h1_seal_policy import is_h1_benchmark_required; raise SystemExit(0 if is_h1_benchmark_required(Path('$KING_ROOT')) else 1)" 2>/dev/null; then
  SEAL_POLICY_OFF=1
fi

if ! king_benchmark_running; then
  echo "[retire] Kein Benchmark-Prozess aktiv"
  exit 0
fi

PID="$(king_benchmark_pid)"
ELAPSED="$(king_benchmark_elapsed_s 2>/dev/null || echo 0)"
CSV_OK=0
king_csv_ready && CSV_OK=1

PROGRESS_PHASE="unknown"
if [[ -f "$KING_ROOT/evidence/h1_benchmark_progress.json" ]]; then
  PROGRESS_PHASE="$("$KING_PY" -c "
import json
from pathlib import Path
p = Path('$KING_ROOT/evidence/h1_benchmark_progress.json')
print(json.loads(p.read_text()).get('phase') or 'unknown')
" 2>/dev/null || echo unknown)"
fi

OVER_ETA=0
"$KING_PY" -c "
from pathlib import Path
from analytics.king_hardware import benchmark_timing
t = benchmark_timing(Path('$KING_ROOT'))
raise SystemExit(0 if t.get('benchmark_over_eta') else 1)
" 2>/dev/null && OVER_ETA=1

RETIRE=0
REASON=""
if [[ "$SEAL_POLICY_OFF" -eq 1 ]]; then
  RETIRE=1
  REASON="Seal-Policy optional — Benchmark nicht mehr nötig (control/h1_seal_policy.json)"
elif [[ "$CSV_OK" -eq 1 ]]; then
  REASON="CSV bereits da — nicht beenden"
elif [[ "$PROGRESS_PHASE" == "legacy_unknown" ]] || [[ "$PROGRESS_PHASE" == "unknown" ]]; then
  if [[ "$OVER_ETA" -eq 1 ]]; then
    RETIRE=1
    REASON="Legacy ohne echten Progress, über ETA (${ELAPSED}s), kein CSV"
  fi
elif [[ "$OVER_ETA" -eq 1 ]] && [[ "$ELAPSED" -gt 5400 ]]; then
  RETIRE=1
  REASON="über ETA und hung-Schwelle (${ELAPSED}s), kein CSV"
fi

echo "[retire] PID=$PID elapsed=${ELAPSED}s csv_ok=$CSV_OK phase=$PROGRESS_PHASE over_eta=$OVER_ETA"
echo "[retire] Urteil: $REASON"

if [[ "$RETIRE" -eq 0 ]]; then
  echo "[retire] Lauf behalten — noch nicht retire-fähig"
  exit 2
fi

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ "$DRY" -eq 1 ]]; then
  echo "[retire] dry-run — würde SIGTERM an PID $PID senden"
  exit 0
fi

kill -TERM "$PID" 2>/dev/null || true
sleep 3
if kill -0 "$PID" 2>/dev/null; then
  echo "[retire] SIGTERM ignoriert — SIGKILL"
  kill -KILL "$PID" 2>/dev/null || true
fi

cat <<EOF | king_write_evidence "evidence/king_legacy_benchmark_retired_latest.json"
{
  "schema_version": 1,
  "retired_at_utc": "$NOW",
  "ok": true,
  "pid": $PID,
  "elapsed_s": $ELAPSED,
  "reason_de": "$REASON",
  "next_action_de": "bash tools/king_ops.sh h1-seal (AA_H1_UNLOAD_OLLAMA=1 AA_H1_GPU_RETURNS=1)",
  "lesson_de": "Legacy CPU-only ohne Prep-Progress — Neustart mit king_h1_seal"
}
EOF

"$KING_PY" -c "
from pathlib import Path
from aa_safe_io import atomic_write_json
from datetime import datetime, timezone
root = Path('$KING_ROOT')
atomic_write_json(root / 'evidence/h1_benchmark_progress.json', {
    'status': 'retired',
    'phase': 'legacy_retired',
    'reason_de': '$REASON',
    'updated_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
})
" 2>/dev/null || true

rm -f "$KING_LOCK_DIR/h1_watch_bg.pid" "$KING_LOCK_DIR/benchmark_hung_logged.flag" 2>/dev/null || true
echo "[retire] PID $PID beendet — Evidence: evidence/king_legacy_benchmark_retired_latest.json"
