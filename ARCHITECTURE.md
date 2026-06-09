# Active Alpha — Architecture

This document explains how the modular codebase fits together, which phases run in parallel, and which must stay serial for economic correctness.

See also [PERFORMANCE.md](PERFORMANCE.md) for cache layout and tuning.

## Module map

| Module | Responsibility |
|--------|----------------|
| `active_alpha_model.py` | Compatibility wrapper; re-exports public API |
| `aa_config.py` | `BacktestConfig`, CLI parsing, `BacktestConfig.from_args()`, capital-curve helpers |
| `aa_constants.py` | Sector/issuer maps, `FEATURE_COLUMNS`, ticker normalization |
| `aa_universe.py` | Ticker loading, PIT membership, universe filters |
| `aa_features.py` | Download, feature engineering, `build_or_load_features()`, caches, ranking |
| `aa_models.py` | `make_model`, `fit_predict` |
| `aa_parallel.py` | `ProcessPoolSession`, worker context, `resolve_n_jobs` |
| `aa_portfolio.py` | Selection, caps, turnover, tail-prune, cluster overlay |
| `aa_backtest_ml.py` | Phase A: walk-forward ML prediction cache |
| `aa_backtest.py` | Phase A/B/C walk-forward, `run_research_pipeline()`, path simulation, naive baselines |
| `aa_reporting.py` | Metrics, benchmarks, bootstrap, `ReportingPipeline`, reports |
| `aa_execution.py` | Trading-212 costs, `PhaseTimings`, run manifest |
| `aa_integrity.py` | Calendar integrity, prediction-cache coverage |
| `aa_run_provenance.py` | `run_id`, `runs/<id>/`, `latest_validated_run.json` |
| `aa_ops_validation.py` | Fast-Path analytical validity gate |
| `aa_variant_id.py` | Canonical variant IDs (`R3_w070_q070_noexit`, …) |
| `aa_data_quality_gate.py` | PIT data-quality warnings before formal compares |
| `aa_dashboard.py` | Console progress dashboard |

## End-to-end pipeline

```text
load_tickers
  → build_or_load_features (price cache, feature cache, or fresh build)
  → apply_dynamic_cluster_overlay
  → features.parquet
  → run_research_pipeline (Phase A ML, Phase B path, Phase C naive)
  → write_backtest_core_outputs + run_backtest_reporting
  → signal export (mode signal/both)
```

## Walk-forward phases (A / B / C)

| Phase | What | Parallel? | Why |
|-------|------|-----------|-----|
| **A — ML** | `fit_predict` + `select_portfolio` per rebalance | Yes | Rebalances are independent given features |
| **B — Path** | Turnover, costs, exposure path | **No** | Each rebalance needs `prev_weights` from the prior step |
| **C — Naive** | Momentum baseline variants | Yes | Independent of Phase B ordering |

Phase B uses vectorized daily PnL (`R @ w`) but remains a single-threaded loop over rebalance dates.

## Process pool lifecycle

One `ProcessPoolSession` per model run:

1. Pool opens after tickers are known (bootstrap-only workers).
2. **Feature engineering** — workers get benchmark/sector context; ticker tasks run on `_ACTIVE_POOL`.
3. **Rank / cluster / ML / naive** — workers rebound to shared `features` + `returns` via `load_backtest_state()`.
4. Pool closes at end of run.

This avoids repeated Windows `spawn` cost from separate pools per phase.

Worker globals live in `ParallelRunContext` (`_CTX` in `aa_parallel.py`).

## Caches (three layers)

| Cache | Scope | Invalidates when |
|-------|-------|------------------|
| Price | Shared or `out_dir/price_cache` | Ticker list, start date, TTL |
| Feature | Shared fingerprint dir or `out_dir` | Universe, horizon, membership, schema |
| Prediction | Per `out_dir` | Feature fingerprint + ML/portfolio params |

Policy/slippage/fee sweeps can reuse prediction cache; see PERFORMANCE.md.

## Robustness lab

`run_robustness_tests.py` runs many variants with:

- Shared feature/price cache (`--shared-cache-dir`)
- Parallel variant jobs (`--parallel-jobs`, max 4)
- Resume support (`--skip-completed`)

Each variant still writes its own reports under `robustness_results_trading212/<name>/`.

## Operational entry points

| Command | Purpose |
|---------|---------|
| `run_active_alpha_model.bat` | Standard backtest + signal |
| `run_robustness_tests.bat` | Stress matrix |
| `active_alpha_model.py --dry-run` | Config preview |
| `active_alpha_model.py --cache-status` | Cache validity snapshot |
| `run_quality_gate.bat` / `tools/run_quality_gate.py` | pytest + self-test + core check |
| `show_active_alpha_config.bat` | Human-readable settings |
| `check_active_alpha_core.py` | Compatibility gate |

## Config validation

`BacktestConfig.from_args()` centralizes CLI → config mapping. `BacktestConfig.__post_init__()` rejects inconsistent inputs early (fee model, capital, position caps, `top_k` vs `universe_top_n`).

Optional reporting steps write both `reporting_errors.txt` (human traceback) and `reporting_errors.json` (structured, CI-friendly). The reporting block is orchestrated by `ReportingPipeline` / `run_backtest_reporting()` in `aa_reporting.py`.

At run start the resolved config (including parallel/cache flags) is written to `run_config_snapshot.txt` via `write_run_config_snapshot()`.

## Runtime profiles (hardware / EXE isolation)

`aa_runtime_profile.py` defines budgets so batch research does not starve **Marktanalyse.exe**:

| Profile | Backend | Reserve cores | Variant parallel | Priority |
|---------|---------|---------------|------------------|----------|
| `exe` | thread | 0 | 1 | normal |
| `research` | process | 2 | 1 | normal |
| `validation` | process | 4 | 3 | below_normal |
| `background` | process | 6 | 1 | idle |

- Env: `AA_RUNTIME_PROFILE`, `AA_RESERVE_CPU_CORES`, `AA_VALIDATION_PARALLEL_JOBS`
- Validation orchestrator detects an open EXE via `is_interactive_session_running()` and downgrades to `background`
- Batch lock file `.active_alpha_batch.lock` marks heavy matrix runs; EXE keeps Fast-Path/cache-first behaviour
- Extend `PROFILES` for future tiers (GPU, cloud agents) without changing orchestrators

## EXE Schritt 6 (Laufplan)

Launcher step `run` = voller Backtest. Kurzpfade in `decide_run_plan()`:

| Modus | Wann | Dauer |
|-------|------|-------|
| `results` | Daten OK + Integrität PASS | Sekunden |
| `refresh_signal` | Preise veraltet, Integrität PASS | Minuten (Preise + `--mode signal`) |
| `analyze` / `refresh_analyze` | Keine gültige Analyse | ~10–20 min |

`AA_SIGNAL_REFRESH_ON_STALE_DATA=1` (Default) vermeidet unnötigen Voll-Backtest.

## Realtime-Daten (Roadmap, nicht implementiert)

Geplante Schichten — Offline-Backtest bleibt Referenz, Live-Pfad getrennt:

1. **Ingest** — Streaming/Batch-API → `price/live/` + Append-only Log
2. **Feature-Increment** — letzte N Tage aus Cache, nicht 2012 neu
3. **Online-Inferenz** — `--mode signal` + warm prediction cache (kein Walk-forward)
4. **Feedback** — Signal vs. Realized Return loggen → periodisches Retrain (Batch, nicht bei jedem EXE-Start)
5. **Governance** — Live-Signale markiert `provisional` bis nächster PASS-Backtest

## Intentionally serial

Do **not** parallelize these without changing economics:

- Walk-forward portfolio path (Phase B)
- Turnover limits that depend on prior weights
- Buy/hold spread and residual hygiene applied sequentially per rebalance

## Integrity and run provenance

Each backtest run writes to `runs/<run_id>/` first:

1. Phase A/B/C via `run_research_pipeline`
2. `validate_backtest_calendar_integrity()` — must PASS before `backtest_report.txt` is published
3. `write_run_manifest()` with code/config fingerprints
4. On PASS only: `latest_validated_run.json` pointer + sync to `--out-dir`

`ml_retrain_every > 1`: ML fits every Nth rebalance; intermediate rebalances re-select on the current snapshot using forwarded predictions.

GUI portfolio amounts use `target_weight × capital` (no silent 100% normalization); cash is the remainder.
