# External Review Approval — V2R

Review date: 2026-05-30

## Reviewed predecessor artifact

- Predecessor phase: `V2_COST_STRESS_AND_ROBUSTNESS_ENGINE`
- Artifact: `codex_v2_robustness_review.zip`
- Observed external SHA-256: `3ac4b5048b60ff72d826535968fb23b10102d07e2fdc63e7d09725a0402f5a94`
- Sidecar verification: PASS

## Review decision

V2 is not approved for transition to V3.

## Confirmed positive findings

- V2 completed through the controlled state machine.
- V1R3 was externally sealed.
- Hooks remain disabled.
- All automation flags remain disabled.
- Champion remains `R3_w075_q065_noexit`.
- V3 was not started.
- New V2 Evidence modules write under `control/evidence/`.

## Required remediation

1. Cost-Stress must not pass using unverified Challenger turnover proxies.
2. Deflated Sharpe Ratio must be frequency-consistent, probabilistically interpreted and based on auditable trial counts.
3. Trial counting must not use unexplained hard-coded additions.
4. Robustness claims must distinguish partial subperiod screens from validated robustness evidence.
5. Unified Evidence output must not simultaneously report Cost-Stress PASS and COST_STRESS_NOT_EVALUATED.
6. Review package must include reproducible compact input data used for V2R computations.
7. Pipeline and protected-hash evidence must be included in the new review package.

## Authorized execution

Execute only:

`V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION`

## Prohibited

- V3 or later execution
- model training or model recalculation
- historical backtest or validation-matrix execution
- M1 recalculation
- research, replay, shadow or paper jobs
- promotion or rollback
- any trading or broker activity
- EXE build or execution
- champion change
- any automation-flag enablement
- productive signal-weight or economic-model-parameter change
- scheduled or background Codex automation
