#!/usr/bin/env bash
# Projekt-Tune — verify → clean → governance → status → watch (safe, efficient).
# Usage: bash tools/king_tune.sh [--no-watch]
set -euo pipefail
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_assert_project_root

NO_WATCH=0
[[ "${1:-}" == "--no-watch" ]] && NO_WATCH=1

echo "=============================================="
echo " KÖNIG TUNE — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================="

echo "[1/8] Verify …"
bash "$KING_ROOT/tools/king_verify.sh"

echo "[2/8] Clean …"
bash "$KING_ROOT/tools/king_clean.sh"

echo "[3/8] Governance …"
"$KING_PY" "$KING_ROOT/tools/sync_strategic_governance.py" 2>/dev/null || true

echo "[4/8] Tier sync …"
"$KING_PY" -c "
from pathlib import Path
from analytics.alpha_model_entfaltung_32b import apply_tier_to_llm_config
apply_tier_to_llm_config(Path('$KING_ROOT'))
print('  local_llm.json OK')
" 2>/dev/null || true

echo "[5/8] Status …"
bash "$KING_ROOT/tools/king_status.sh" | tail -14

echo "[6/8] Prognose-Freischaltung …"
bash "$KING_ROOT/tools/king_ops.sh" prognosis run 2>/dev/null | head -3 || echo "  Prognose: übersprungen (T212/Trust)"

echo "[7/8] H1-Prep (wenn Seal offen, kein Benchmark) …"
if ! king_h1_sealed && ! king_benchmark_running && ! king_csv_ready; then
  bash "$KING_ROOT/tools/king_h1_prep.sh" 2>/dev/null | tail -8 || true
else
  echo "  übersprungen (sealed/csv/benchmark aktiv)"
fi

SEAL_REQUIRED=1
if ! "$KING_PY" -c "from pathlib import Path; from analytics.h1_seal_policy import is_h1_seal_required; raise SystemExit(0 if is_h1_seal_required(Path('$KING_ROOT')) else 1)" 2>/dev/null; then
  SEAL_REQUIRED=0
fi

WATCH_STARTED=0
if [[ "$SEAL_REQUIRED" -eq 1 ]] && [[ "$NO_WATCH" -eq 0 ]] && king_benchmark_running && ! king_csv_ready && ! king_h1_sealed; then
  if king_watch_bg_running; then
    echo "[8/8] H1-Watch läuft bereits (PID $(cat "$KING_LOCK_DIR/h1_watch_bg.pid"))"
    WATCH_STARTED=1
  else
    echo "[8/8] H1-Watch Hintergrund (Benchmark PID $(king_benchmark_pid)) …"
    king_with_lock h1_watch_bg bash -c "
      nohup bash '$KING_ROOT/tools/king_h1_seal.sh' --wait >>'$KING_ROOT/evidence/king_h1_watch.log' 2>&1 &
      echo \$! >'$KING_LOCK_DIR/h1_watch_bg.pid'
    "
    WATCH_STARTED=1
  fi
elif [[ "$SEAL_REQUIRED" -eq 1 ]] && king_csv_ready && ! king_h1_sealed; then
  echo "[8/8] CSV da — h1-seal …"
  bash "$KING_ROOT/tools/king_h1_seal.sh"
elif [[ "$NO_WATCH" -eq 1 ]]; then
  echo "[8/8] H1-Watch übersprungen (--no-watch)"
elif king_h1_sealed; then
  echo "[8/8] H1-Watch übersprungen (sealed)"
else
  echo "[8/8] H1-Watch übersprungen (idle)"
fi

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat <<EOF | king_write_evidence "evidence/king_tune_latest.json"
{
  "schema_version": 1,
  "tuned_at_utc": "$NOW",
  "ok": true,
  "watch_bg_started": $([ "$WATCH_STARTED" -eq 1 ] && echo true || echo false),
  "bash_de": "bash tools/king_ops.sh tune"
}
EOF

PULSE="$(king_sync_network bash 2>/dev/null || echo "")"
[[ -n "$PULSE" ]] && echo "[netz] $PULSE"

echo "[OK] Tune fertig — evidence/king_tune_latest.json"
