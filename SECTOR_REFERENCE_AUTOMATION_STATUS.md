# Sector Reference Automation — Status

**Phase:** S0–S8 complete (infrastructure only)  
**Review:** `AWAITING_EXTERNAL_REVIEW`  
**Champion / signal weights:** unchanged (`R3_w075_q065_noexit` governance)

## Handoff

| Item | Path |
|------|------|
| Plan | `docs/SECTOR_REFERENCE_AUTOMATION_PLAN.md` |
| Acceptance | `evidence/sector_reference_acceptance_s8.json` |
| Rollout | `evidence/sector_reference_rollout_summary.json` |
| Review ZIP | `codex_sector_reference_automation_review.zip` (+ `.sha256`) |

## Re-run acceptance

```powershell
.venv\Scripts\python.exe tools\run_sector_reference_acceptance_s8.py --write-evidence --sync-refresh-latest --pytest
```

## Re-run rollout (if stale)

```powershell
.venv\Scripts\python.exe tools\run_sector_reference_rollout_s7.py
```
