# CODEX V2R Statistical Validity Report

Phase: `V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION`  
Generated: 2026-05-30 (UTC)

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL

## Remediation summary

V2R corrected cost-stress, deflated Sharpe ratio (DSR), trial counting, robustness evidence boundaries, and unified evidence status blockers per external review findings.

## V2 external seal

| Field | Value |
|-------|-------|
| Predecessor | `V2_COST_STRESS_AND_ROBUSTNESS_ENGINE` |
| Sealed by | `EXTERNAL_REVIEW_APPROVAL_V2R.md` |
| Review ZIP SHA-256 | `3ac4b5048b60ff72d826535968fb23b10102d07e2fdc63e7d09725a0402f5a94` |
| V2_EXTERNAL_SEALED | YES |

## Cost-Stress (V2R)

| Gate | Result |
|------|--------|
| `COST_STRESS_GATE.pass` | false |
| `evaluation_status` | NOT_EVALUABLE |
| Blocker | CHALLENGER_TURNOVER_NOT_VERIFIED |

Champion turnover proxy for `MOM_63_TOP12` is excluded from gate evidence. Sensitivity analysis retained under `sensitivity_analysis.proxy_turnover_results` with label `NOT_GATE_EVIDENCE`.

Baseline cost treatment verified for Champion and M1 from readable backtest reports.

## Multiple-Testing / DSR (V2R)

| Field | Value |
|-------|-------|
| `tested_variant_count` | 13 (derived from challenger_report + naive columns) |
| `periodic_sharpe` (DSR input) | 0.0635 (daily frequency) |
| `annualized_sharpe_display_only` | 1.008 |
| `dsr_probability` | 0.841 |
| `dsr_required_probability` | 0.95 |
| Status | FAIL |
| Blocker | DSR_BELOW_REQUIRED_CONFIDENCE |
| PBO_STATUS | NOT_EVALUABLE |

## Robustness (V2R)

| Component | Result |
|-----------|--------|
| `SUBPERIOD_STABILITY_SCREEN.pass` | true |
| `ROBUSTNESS_EVIDENCE.pass` | false |
| `ROBUSTNESS_EVIDENCE.status` | PARTIAL_ONLY |
| Blockers | COST_STRESS_GATE_NOT_PASSED |

Subperiod screen alone does not constitute full robustness evidence.

## Unified evidence status

| Field | Value |
|-------|-------|
| `current_evidence_stage` | BACKTESTED |
| `promotion_eligible` | false |
| `paper_eligible` | false |
| `real_money_eligible` | false |
| Historical `COST_STRESS_NOT_EVALUATED` | resolved/superseded |
| Current blockers | CHALLENGER_TURNOVER_NOT_VERIFIED, DSR_BELOW_REQUIRED_CONFIDENCE, P9_NOT_EXTERNALLY_REVIEWED, … |

## Controller state after V2R

| Field | Value |
|-------|-------|
| `current_executed_phase` | V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION |
| `expected_next_phase` | V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION |
| `execution_status` | AWAITING_EXTERNAL_REVIEW |
| `last_review_zip` | codex_v2r_statistical_validity_review.zip |
| `NEXT_PHASE_AUTHORIZED` | false |

## Tests

159 regression tests passed. Output: `CODEX_V2R_TEST_OUTPUT.txt`.

## Protected artifacts

Pre/post SHA-256 recorded in `CODEX_V2R_PROTECTED_HASHES_BEFORE.json` and `CODEX_V2R_PROTECTED_HASHES_AFTER.json`. No protected production files modified.

## Prohibited actions (confirmed not executed)

V3 not started. No operative jobs, EXE build/execution, promotion, champion change, or automation enablement.
