# R0 Production Cutover Runbook

Generated: 2026-06-05T15:39:08+00:00

## Target champion
`R0_LEGACY_ENSEMBLE`

## Rollback
Restore pointer to `control/rollback/r3_last_known_good/latest_validated_run.json` (R3_w075_q065_noexit).

## Pre-cutover
- M5 gate_matrix PASS
- M6 shadow PASS (accelerated replay)
- M7 paper PASS (accelerated proxy)
- EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_20260605.md present

## Cutover steps (M9)
1. Update `model_output_sp500_pit_t212/latest_validated_run.json` to R0 run_dir: `E:\active_alpha_model\validation_runs\20260604T210245Z_R0_LEGACY_ENSEMBLE`
2. Verify signal dry-run
3. Document first production window

## Safety
Auto-promotion disabled. Real-money prohibited unless separately authorized.
