# R0 OS / Desktop Rollout Runbook

Generated: 2026-06-05T15:39:08+00:00

## Scope
WSL-first migration complete. Windows retained for EXE review.

## Host layout
- WSL: `~/active_alpha_model` (compute)
- Windows: `E:\active_alpha_model` (sync source)

## Rollout checklist
1. WSL conductor: `bash tools/wsl_conductor.sh status`
2. Marktanalyse.exe hash verified (`Marktanalyse.exe.sha256`)
3. Champion: `R0_LEGACY_ENSEMBLE` post-M9

## Rollback
See `docs/R0_PRODUCTION_CUTOVER_RUNBOOK.md`
