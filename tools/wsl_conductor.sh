#!/usr/bin/env bash
# WSL canonical conductor — ONE entry, no .bat / PowerShell / rival drivers.
# Usage:
#   bash tools/wsl_conductor.sh setup          # first-time host prep
#   bash tools/wsl_conductor.sh m1             # M1 matrix (current Windows-equivalent run)
#   bash tools/wsl_conductor.sh m1-fast        # post-M1 seal + AA_POST_M1_PERF=1
#   bash tools/wsl_conductor.sh autoseal       # poll + seal + M2 chain
#   bash tools/wsl_conductor.sh status         # hardware + seal snapshot
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Fail-closed: Linux/WSL = compute only (no T212 POST unless AA_LINUX_ALLOW_LIVE_ORDERS=1).
# shellcheck disable=SC1091
source "$ROOT/tools/linux_env.sh"
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

cmd="${1:-status}"
shift || true

case "$cmd" in
  setup)
    exec bash "$ROOT/tools/setup_wsl_host.sh"
    ;;
  m1)
    exec "$PY" -u tools/run_validation_matrix.py \
      --phase matrix --variant M1_MOM_BLEND_MATCHED_CONTROLS \
      --parallel-jobs 1 --cpu-cores "$(nproc)"
    ;;
  m1-fast)
    export AA_POST_M1_PERF=1
    exec "$PY" -u tools/run_validation_matrix.py \
      --phase matrix --variant M1_MOM_BLEND_MATCHED_CONTROLS \
      --parallel-jobs 1 --cpu-cores "$(nproc)"
    ;;
  autoseal)
    exec "$PY" -u tools/_m1_autoseal.py
    ;;
  m3)
    exec "$PY" -u tools/run_r0_migration_phase_m3.py "$@"
    ;;
  m3-daily)
    exec "$PY" -u tools/run_validation_matrix.py \
      --phase matrix --variant DAILY_ALPHA_H1 \
      --parallel-jobs 1 --cpu-cores "$(nproc)"
    ;;
  orchestrator)
    exec "$PY" -u tools/run_r0_migration_phase_orchestrator.py
    ;;
  accel)
    exec "$PY" -u tools/run_r0_migration_phases_m5_m12.py chain
    ;;
  predict)
    exec "$PY" -u tools/run_tomorrow_prediction.py "$@"
    ;;
  live-ops)
    exec bash "$ROOT/tools/linux_live_ops.sh" "$@"
    ;;
  status)
    exec "$PY" -u tools/r0_migration_status.py
    ;;
  verify)
    exec "$PY" -u tools/preflight_wsl_migration.py
    ;;
  post-m1)
    export AA_POST_M1_PERF=1
    exec bash "$ROOT/tools/run_wsl_post_m1_matrix.sh"
    ;;
  *)
    echo "Unknown: $cmd (setup|m1|m1-fast|autoseal|status|verify|post-m1|m3|m3-daily|orchestrator|accel|predict|live-ops)" >&2
    exit 2
    ;;
esac
