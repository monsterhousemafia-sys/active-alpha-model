#!/usr/bin/env bash
# Post-M1/M2 WSL runs: enables returns-fast-path + path-sim-checkpoint via AA_POST_M1_PERF=1.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export AA_POST_M1_PERF=1
exec python3 -u tools/run_validation_matrix.py \
  --phase matrix \
  --variant M1_MOM_BLEND_MATCHED_CONTROLS \
  --parallel-jobs 1 \
  --cpu-cores "$(nproc)"
