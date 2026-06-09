# Active Alpha — Baseline Reference (Phase 0)

Use this template before/after optimization changes so every step stays comparable.

## Reference run checklist

1. Record config source: `active_alpha_settings.bat` + optional `active_alpha_user_config.bat`
2. Run gate: `check_active_alpha_core.py` and `pytest tests/ -q`
3. Execute one full backtest into a dedicated `out_dir` (not shared with robustness variants)
4. Archive `phase_timings.json`, `backtest_report.txt`, and `run_config_snapshot.txt`

## Suggested baseline command

```powershell
.venv\Scripts\python.exe active_alpha_model.py `
  --mode both `
  --membership-mode strict `
  --reuse-feature-cache `
  --reuse-prediction-cache `
  --out-dir model_output_baseline
```

Or use `run_active_alpha_model.bat` with `AA_BACKTEST_OUT_DIR=model_output_baseline`.

## Metrics to record

Copy from `backtest_report.txt`:

| Metric | Baseline value | Date |
|--------|----------------|------|
| strategy_cagr | | |
| strategy_sharpe_0rf | | |
| strategy_max_drawdown | | |
| information_ratio | | |
| approx_annual_turnover | | |
| avg_portfolio_exposure | | |

From `phase_timings.json` (sections_seconds):

| Section | Seconds |
|---------|---------|
| download | |
| feature_build | |
| walkforward_phase_a_ml | |
| walkforward_phase_b_path | |
| walkforward_phase_c_naive | |
| reporting | |
| total_run | |

## Acceptance after a change

A performance or refactor step is OK when:

- All tests and `--self-test` pass
- `check_active_alpha_core.py` passes
- Core metrics match within tolerance (same seed/config):
  - CAGR ± 0.2% absolute
  - Sharpe ± 0.05
  - Rebalance count unchanged
- `phase_timings.json` shows expected speedup (or no regression > 5% without cause)

## Compare two runs

```powershell
.venv\Scripts\python.exe active_alpha_model.py --cache-status --out-dir model_output_baseline
.venv\Scripts\python.exe active_alpha_model.py --cache-status --out-dir model_output_after_change
```

## Robustness baseline variant

The lab baseline variant name:

`threshold_tail005_fx0_slip2_top100_beta125_k12`

Warm shared caches first:

```powershell
python run_robustness_tests.py --only threshold_tail005_fx0_slip2_top100_beta125_k12 --parallel-jobs 1
```

Then resume the full matrix:

```powershell
python run_robustness_tests.py --skip-completed --parallel-jobs 2
```
