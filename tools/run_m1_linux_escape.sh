#!/usr/bin/env bash
# M1 Linux escape hatch — run AFTER `wsl --install` (or on any Linux host with repo mounted).
# Same canonical flags as run_validation_matrix.py + m1_fast_seal.flag semantics.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PY:-python3}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${ROOT}/validation_runs/${STAMP}_M1_MOM_BLEND_MATCHED_CONTROLS"
CACHE_SRC="$(ls -d "${ROOT}"/validation_runs/*_M1_MOM_BLEND_MATCHED_CONTROLS 2>/dev/null | sort | tail -1 || true)"
mkdir -p "$OUT"
if [[ -n "$CACHE_SRC" && -f "${CACHE_SRC}/prediction_cache.pkl" ]]; then
  cp -f "${CACHE_SRC}/prediction_cache.pkl" "${CACHE_SRC}/prediction_cache_meta.json" "$OUT/"
  echo "[escape] seeded prediction cache from $(basename "$CACHE_SRC")"
fi
exec "$PY" -u active_alpha_model.py \
  --mode backtest \
  --ticker-source sp500_pit \
  --membership-file ticker_membership.csv \
  --membership-mode strict \
  --benchmark SPY \
  --start 2012-01-01 \
  --universe-mode diy_pit_liquidity \
  --universe-top-n 100 \
  --rebalance-every 5 \
  --horizon 10 \
  --train-years 7 \
  --ml-retrain-every 2 \
  --alpha-model-mode ensemble \
  --exposure-controller gradual_alpha \
  --beta-cap-mode dynamic \
  --cluster-mode static \
  --cluster-constraint-mode static_only \
  --slippage-bps 2 \
  --market-impact-bps 0 \
  --fee-model trading212_us \
  --backtest-capital 100000 \
  --research-backtest-capital 100000 \
  --reproducibility-mode strict \
  --random-seed 42 \
  --n-jobs 1 \
  --cpu-cores "$(nproc)" \
  --parallel-profile high \
  --parallel-backtest-backend thread \
  --reuse-feature-cache \
  --skip-download-if-cached \
  --skip-feature-parquet-write \
  --no-plot --no-gui --plain-progress \
  --no-naive-momentum-baseline \
  --no-statistical-diagnostics \
  --no-custom-benchmarks \
  --minimal-backtest-reporting \
  --no-run-manifest \
  --no-naive-overlap \
  --reuse-prediction-cache \
  --shared-cache-dir "${ROOT}/robustness_results_trading212/_shared_cache" \
  --out-dir "$OUT" \
  --risk-off-selection-mode legacy \
  --risk-off-gate-mode legacy
