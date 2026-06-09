# CODEX V3 Preflight — Controlled Forward Monitoring Foundation

Generated: 2026-05-30 (UTC)

## V2R external seal

| Field | Value |
|-------|-------|
| Predecessor phase | `V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION` |
| Review ZIP | `codex_v2r_statistical_validity_review.zip` |
| Observed external SHA-256 | `46005fd19828e5ac43e4e28c4c5709aa5b3051936be34e03797ba6c4ba8a0bdf` |
| Sidecar verification | PASS |

## V2R Git checkpoint

| Field | Value |
|-------|-------|
| Checkpoint commit | `956c35eb4c25024e28efd53748a0aec3963aab41` |
| Checkpoint message | `fix: validate cost stress and statistical evidence before V3` |
| Branch | `codex/v2r-statistical-validity-remediation` |
| GIT_V2R_CHECKPOINT_VERIFIED | YES |

Uncommitted changes at preflight are limited to unrelated sidecar/git-status files, not V2R evidence or controller state.

## Hook status

- `.cursor/hooks.json`: empty hooks — **DISABLED**

## Automation flags

| Flag | Value |
|------|-------|
| auto_research_enabled | false |
| auto_promote_paper_enabled | false |
| auto_promote_signal_enabled | false |
| auto_execute_real_money_enabled | false |
| PROMOTION_ALLOWED | false |
| OPERATIVE_JOBS_ALLOWED | false |
| SHADOW_COLLECTION_ALLOWED | false |
| PAPER_SIMULATION_ALLOWED | false |

## Champion and evidence

| Field | Value |
|-------|-------|
| Champion | `R3_w075_q065_noexit` |
| Evidence stage | BACKTESTED |
| Source classification | PREEXISTING_UNREVIEWED |

### Active blockers (preserved)

- CHALLENGER_TURNOVER_NOT_VERIFIED
- DSR_BELOW_REQUIRED_CONFIDENCE
- ROBUSTNESS_NOT_PASSED (PARTIAL_ONLY)
- P9_NOT_EXTERNALLY_REVIEWED
- COST_STRESS_GATE NOT_EVALUABLE

## Helper bypass audit

Static audit via `aa_v2_bypass_audit.audit_helper_scripts` — required before V3 run.

## Baseline cost reports

| Path | Present |
|------|---------|
| `model_output_sp500_pit_t212/backtest_report.txt` | NO |
| `validation_runs/.../backtest_report.txt` | NO |

Note: `BASELINE_COST_REPORT_NOT_EXTERNALLY_INCLUDED` — cost stress remains blocked via Challenger turnover.

## Operational confirmation

- No operative jobs, research, shadow, paper or EXE execution
- No promotion or champion change
- Preflight result: **PASS**
