# CODEX V2 Source Inventory

Generated: 2026-05-30 (UTC)

## Variants

| Variant | Returns | Observations | Turnover source | Available |
|---------|---------|--------------|-----------------|-----------|
| `R3_w075_q065_noexit` | `model_output_sp500_pit_t212/strategy_daily_returns.csv` | 1860 | `backtest_decisions.csv` | YES |
| `M1_MOM_BLEND_MATCHED_CONTROLS` | `validation_runs/.../mom_blend_matched_controls_daily_returns.csv` | 1860 | `backtest_decisions.csv` (M1 run) | YES |
| `MOM_63_TOP12` | `runs/.../naive_momentum_daily_returns.csv` (`NAIVE_MOMENTUM_MOM_63_TOP12`) | 1860 | Champion turnover proxy | YES |

Aligned calendar: **1860** observations (2019-01-03 → 2026-05-28).

## Cost assumptions

- Baseline costs **already embedded** in return series (`cost_bps=10`, `slippage_bps=2`, `trading212_us`).
- V2 stress applies **incremental** bps on rebalance turnover only.
- Config hash: `d4c73d780bedcb309869362ff9e90d7189b76acf00d120a317915430bff6210e`

## Candidate matrix

- `control/challenger_report.json`: 7 matrix variants compared.
- PBO/CSCV inputs: **not available** (`INSUFFICIENT_CANDIDATE_MATRIX_FOR_PBO`).

## Source file hashes

See machine-readable `control/evidence/v2_source_inventory.json`.
