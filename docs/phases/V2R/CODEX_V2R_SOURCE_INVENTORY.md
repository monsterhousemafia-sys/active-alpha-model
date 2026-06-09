# CODEX V2R Source Inventory

Phase: `V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION`  
Generated: 2026-05-30 (UTC)

## Reproducible computation inputs

| Path | SHA-256 (if present) | Used for |
|------|----------------------|----------|
| `model_output_sp500_pit_t212/strategy_daily_returns.csv` | see v2_source_inventory | Champion cost stress / robustness |
| `model_output_sp500_pit_t212/backtest_decisions.csv` | see v2_source_inventory | Champion turnover |
| `model_output_sp500_pit_t212/backtest_report.txt` | see cost_stress_status | Baseline cost verification (Champion) |
| `validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/mom_blend_matched_controls_daily_returns.csv` | see v2_source_inventory | M1 returns |
| `validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/backtest_decisions.csv` | see v2_source_inventory | M1 turnover |
| `validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/backtest_report.txt` | see cost_stress_status | Baseline cost (M1/Challenger) |
| `runs/20260530T162749569Z_M1_MOM_BLEND_MATCHED_CONTROLS_dec4af3a_012fe917_s2i0_15c6ce/naive_momentum_daily_returns.csv` | see v2_source_inventory | Challenger returns / DSR |
| `control/challenger_report.json` | see multiple_testing_status | Trial count derivation |

## Challenger turnover artifact

No variant-specific Challenger turnover/decision file exists. Gate evidence blocked with `CHALLENGER_TURNOVER_NOT_VERIFIED`. Champion decisions used only in sensitivity analysis (`NOT_GATE_EVIDENCE`).

## Evidence outputs (V2R-updated)

- `control/evidence/v2_source_inventory.json`
- `control/evidence/cost_stress_status.json`
- `control/evidence/multiple_testing_status.json`
- `control/evidence/robustness_status.json`
- `control/evidence/current_evidence_status.json`

## Code modules changed

- `aa_cost_stress.py` — schema v2, verified turnover/cost gates
- `aa_multiple_testing_adjustment.py` — frequency-consistent DSR, auditable trials
- `aa_robustness_evidence.py` — SUBPERIOD_STABILITY_SCREEN vs ROBUSTNESS_EVIDENCE
- `aa_evidence_status.py` — historical vs current blockers
- `aa_vision_phase_catalog.py` — V2R phase in chain

Full hashes: `control/evidence/v2_source_inventory.json`.
