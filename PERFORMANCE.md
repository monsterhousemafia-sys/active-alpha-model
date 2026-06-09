# Active Alpha — Performance & Cache Guide

This document describes the reusable caches, parallel execution model, and when caches are invalidated.

## Quick flags

| Flag | Purpose |
|------|---------|
| `--reuse-feature-cache` | Skip download + feature engineering when fingerprint matches |
| `--force-rebuild-features` | Ignore feature cache and rebuild |
| `--no-feature-cache` | Do not write feature cache after build |
| `--reuse-prediction-cache` | Skip Phase-A ML when fingerprint matches |
| `--force-rebuild-predictions` | Ignore prediction cache |
| `--no-prediction-cache` | Do not write prediction cache |
| `--skip-download-if-cached` | Reuse OHLCV panel in price cache |
| `--price-cache-ttl-hours N` | Price cache TTL (`0` = never expire) |
| `--shared-cache-dir PATH` | Store feature/price caches outside `--out-dir` |
| `--dry-run` | Print resolved config and planned phases, then exit |
| `--minimal-backtest-reporting` | Core CSVs + short report only (validation matrix default) |
| `--backtest-scope path-only` | Phase B only using `--prediction-cache-dir` (cost sweeps) |
| `--n-jobs auto` | Use physical-core worker budget (see below) |

Environment fallback: `AA_SHARED_CACHE_DIR` is used when `--shared-cache-dir` is empty.

## Cache layout

### Single run (default)

When `--shared-cache-dir` is **not** set, caches live in `--out-dir`:

```
out_dir/
  feature_cache.parquet
  returns_cache.parquet
  feature_cache_meta.json
  price_cache/
    ohlcv_panel.parquet
    price_cache_meta.json
  prediction_cache.pkl
  prediction_cache_meta.json
```

### Shared cache (robustness lab)

When `--shared-cache-dir` **is** set:

```
shared_cache_dir/
  price/
    ohlcv_panel.parquet
    price_cache_meta.json
  features/
    fp_<feature_fingerprint>/
      feature_cache.parquet
      returns_cache.parquet
      feature_cache_meta.json
```

Variant-specific outputs (reports, prediction cache, manifests) still go to each variant's `--out-dir`.

The robustness runner defaults to:

`robustness_results_trading212/_shared_cache`

## Cache invalidation rules

### Feature cache (`schema_version = 2`)

Invalidated when any of these change:

- `start`, `benchmark`, universe settings (`universe_mode`, `universe_top_n`, ADV/price/history thresholds)
- `ticker_source`, `ticker_snapshot_date`
- `membership_mode`, membership file content (SHA-256 hash)
- `horizon`, ticker count
- Cache schema version mismatch

**Not** in fingerprint (safe to reuse across policy/cost sweeps): slippage, fees, `top_k`, `alpha_model_mode`, turnover limits.

Use `--force-rebuild-features` after code changes to feature engineering.

### Prediction cache (`schema_version = 1`)

Invalidated when feature fingerprint **or** ML/portfolio selection parameters change (`alpha_model_mode`, `train_years`, `top_k`, exposure controller, rebalance structure, etc.).

Policy and execution-cost sweeps can reuse Phase-A predictions when only slippage/fees/turnover change.

### Price cache

Invalidated when:

- Ticker list or `start` date changes (fingerprint)
- TTL expires (`--price-cache-ttl-hours`, default 24 h)

## Parallel execution

- **`--n-jobs auto`**: min(physical CPU cores, RAM budget). On a Ryzen 3950X use `--cpu-cores 16`, not 32 threads.
- **`--parallel-profile high`**: float32 feature tables + larger pool chunks (recommended with 64 GB RAM).
- **`ProcessPoolSession`**: one process pool per run for ticker feature build → rank → cluster → ML → naive baselines. Workers are rebound in-process after feature engineering (no second Windows spawn).
- **`ParallelRunContext`**: worker globals (`features`, `returns`, `cfg`) loaded once per worker on Windows spawn.

Reporting steps (benchmark comparison, factor regression, diagnostics) run in a small thread pool after the backtest path completes.

## Robustness lab

```bat
run_robustness_tests.bat
```

Useful options on `run_robustness_tests.py`:

```text
--dry-run                  Print commands only
--only baseline            Run matching variant names
--max-variants 3           Limit count
--parallel-jobs 2          Run 2 variants at once (max 4)
--shared-cache-dir PATH    Override shared cache root
```

Recommended workflow:

1. `python run_robustness_tests.py --dry-run --only baseline` — verify commands
2. `python run_robustness_tests.py --only baseline --parallel-jobs 1` — warm shared caches
3. Full matrix with `--parallel-jobs 2` (default)

## Dry-run preview

```bat
.venv\Scripts\python.exe active_alpha_model.py --dry-run --mode both --out-dir model_output_sp500_pit_t212
```

Prints resolved paths, cache flags, worker count, and planned phases without downloading data.

## Timing

Every run writes `phase_timings.json` in `--out-dir` with sections such as:

- `download`, `feature_build`, `cluster_overlay`
- `walkforward_phase_a_ml`, `walkforward_phase_b_path`, `walkforward_phase_c_naive`
- `reporting`, `total_run`

Compare before/after optimization changes using the same config and `out_dir`. See [BASELINE.md](BASELINE.md) for a reference-run template.

## Marktanalyse.exe (frozen launcher)

The Windows launcher (`Marktanalyse.exe`, built via `build_active_alpha_launcher.bat`) runs the same pipeline as `run_active_alpha_model.bat` with frozen-friendly defaults:

| Setting | Frozen default |
|---------|----------------|
| `AA_RUN_MODE` | `both` (backtest + signal) |
| `AA_PARALLEL_BACKTEST_BACKEND` | `thread` (avoids extra process spawn) |
| `AA_SKIP_DOWNLOAD_IF_CACHED` | `1` |
| `AA_N_JOBS` | `auto` |

After each build, `tools/smoke_test_launcher.py` verifies EXE size, version metadata, ETA calibration, and (when model output exists) result chart loading.

Each EXE run writes **`marktanalyse_last_run.log`** in the project root (tee of stdout/stderr).

### ETA calibration in the UI

The Qt dashboard blends live progress with historical **`phase_timings.json`** from the active `--out-dir`:

- Pipeline steps map to timing sections (e.g. `walkforward_phase_a_ml` → ML step).
- When no profile exists, conservative fallback budgets are used (warm-cache EXE run).
- Re-run once on the same machine to improve ETA accuracy for subsequent runs.

Model profile and app version are recorded in the run manifest (`app_version`, `model_profile` from `aa_version.py`).

For module layout and walk-forward phases, see [ARCHITECTURE.md](ARCHITECTURE.md).
