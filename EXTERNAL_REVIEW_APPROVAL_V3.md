# External Review Approval — V3

Review date: 2026-05-30

## Reviewed predecessor artifact

- Predecessor phase: `V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION`
- Artifact: `codex_v2r_statistical_validity_review.zip`
- Observed external SHA-256: `46005fd19828e5ac43e4e28c4c5709aa5b3051936be34e03797ba6c4ba8a0bdf`
- Sidecar verification: PASS

## Review decision

V2R is approved for transition to V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION only.

## Confirmed evidence state

- Champion remains `R3_w075_q065_noexit`.
- AUTO_RESEARCH is DISABLED.
- AUTO_PROMOTE_PAPER is DISABLED.
- AUTO_PROMOTE_SIGNAL is DISABLED.
- AUTO_EXECUTE_REAL_MONEY is DISABLED.
- COST_STRESS_GATE is NOT_EVALUABLE because Challenger-specific turnover is not verified.
- DSR evidence fails the required confidence threshold.
- ROBUSTNESS_EVIDENCE is PARTIAL_ONLY.
- Current evidence stage remains BACKTESTED.
- Promotion, Paper eligibility and Real-Money eligibility remain false.
- V3 was not previously started.

## Scope authorized for V3

V3 may implement only:

- versioned monitoring schemas,
- read-only monitoring readiness/status loaders,
- blocked/not-activated Forward, Shadow and Paper status artifacts,
- data requirements for future observation phases,
- controller support for the later external branch decision:
  - V3S_SHADOW_OBSERVATION_ACTIVATION, or
  - V4_DECISION_COCKPIT_GUI_INTEGRATION,
- unit tests,
- reports and review artifacts.

## Mandatory preflight requirements

Before any implementation change:

1. Verify or create a Git checkpoint for the exact externally reviewed V2R state.
2. Confirm no controller/helper bypass has been introduced.
3. Confirm all Safety flags remain disabled.
4. Confirm Hooks remain disabled.
5. Preserve the current evidence stage as BACKTESTED.
6. Treat the missing Challenger turnover, failed DSR, partial robustness and unreviewed P9 state as active blockers.
7. If referenced baseline-cost backtest report files exist, include them in the V3 review package; otherwise mark the baseline-cost verification claim as externally unverified.

## Not authorized

- V3S Shadow activation
- V3P Paper activation
- V4 GUI implementation
- V5 EXE build
- Research, replay, market-data collection, shadow collection or paper simulation
- Promotion, rollback, trading or broker connectivity
- Champion change
- Automation-flag enablement
- Economic model parameter or productive signal-weight changes
- Scheduled or background Codex automation
