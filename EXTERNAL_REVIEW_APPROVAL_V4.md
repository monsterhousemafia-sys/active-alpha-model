# External Review Approval — V4

Review date: 2026-05-30

## Reviewed predecessor artifact

- Predecessor phase: `V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION`
- Artifact: `codex_v3_monitor_foundation_review.zip`
- Observed external SHA-256: `1a18b63ea3258d0761be168ee74e2093cb992a212aa5ee433ab3e4546886abb4`
- Sidecar verification: PASS

## Review decision

V3 is approved for transition to `V4_DECISION_COCKPIT_GUI_INTEGRATION` only.

V3S Shadow activation is not approved.

## Confirmed current evidence state

- Champion remains `R3_w075_q065_noexit`.
- AUTO_RESEARCH is DISABLED.
- AUTO_PROMOTE_PAPER is DISABLED.
- AUTO_PROMOTE_SIGNAL is DISABLED.
- AUTO_EXECUTE_REAL_MONEY is DISABLED.
- Evidence Stage remains `BACKTESTED`.
- Forward Monitoring is `BLOCKED`.
- Shadow Monitoring is `BLOCKED`; collection has not started.
- Paper Monitoring is `BLOCKED`; simulation has not started.
- Promotion, Paper eligibility and Real-Money eligibility remain false.
- Protected V3 artifacts were unchanged.
- V3 selected no automatic follow-on branch.

## Active blockers that must remain visible in the GUI

- `CHALLENGER_TURNOVER_NOT_VERIFIED`
- `COST_STRESS_GATE_NOT_PASSED`
- `DSR_BELOW_REQUIRED_CONFIDENCE`
- `ROBUSTNESS_NOT_PASSED`
- `P9_NOT_EXTERNALLY_REVIEWED`
- `SHADOW_ACTIVATION_NOT_EXTERNALLY_APPROVED`
- `PAPER_ACTIVATION_NOT_EXTERNALLY_APPROVED`

## Documentation correction required in V4

The separate V3 report stated that referenced baseline-cost backtest reports were not present. The reviewed V3 ZIP in fact contains:

- `model_output_sp500_pit_t212/backtest_report.txt`
- `validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/backtest_report.txt`

and `forward_monitoring_readiness_status.json` records both as present.

This documentation inconsistency must be recorded as corrected in V4. It does not make Cost Stress pass; Cost Stress remains blocked because Challenger-specific turnover is not verified.

## Authorized V4 scope

V4 may:

- seal the V3 review through the approved controller path,
- implement read-only GUI view models and views,
- read existing Evidence, Monitoring, Safety, Experiment and Controller artifacts,
- display blockers, conflicts and missing evidence,
- add export of read-only dashboard/report data where safe,
- add GUI/unit tests using fixtures,
- produce a V4 review package.

## Not authorized

- V3S or V3P activation
- V5 EXE build
- EXE execution
- research, replay, market-data collection, shadow collection or paper simulation
- promotion, rollback, trading or broker connectivity
- champion change
- automation-flag enablement
- economic-model parameter or productive signal-weight changes
- scheduled or background Codex automation
