# External Review Approval — V2

Review date: 2026-05-30

## Reviewed predecessor artifact

- Predecessor phase: `V1R3_AUTHORIZED_COMPLETION_GATE`
- Artifact: `codex_v1r3_authorized_completion_review.zip`
- Observed external SHA-256: `62428f7ef13af102e25e834ab391b30d1cda0e86955e0d5b2edcc3cab875659a`
- Sidecar verification: PASS

## Review decision

V1R3 is approved for transition to V2, subject to the mandatory V2 preflight checks below.

## Confirmed positive findings

- Review chain is modeled as `V1 -> V1R -> V1R2 -> V1R3 -> V2`.
- The reviewed controller requires registered approval, running state, stored PASS test evidence, repeated safety prechecks and a catalog-matching review ZIP before completing a phase.
- Legacy direct completion paths in the supplied controller module are blocked.
- Hooks remain disabled.
- AUTO_RESEARCH, AUTO_PROMOTE_PAPER, AUTO_PROMOTE_SIGNAL and AUTO_EXECUTE_REAL_MONEY remain disabled.
- Champion remains `R3_w075_q065_noexit`.
- Evidence remains `BACKTESTED / PREEXISTING_UNREVIEWED`.
- Promotion, Paper eligibility and Real-Money eligibility remain false.

## Accepted documented representation drift

The externally compared V1R2 and V1R3 copies of `control/evidence/current_evidence_status.json` contain semantically identical JSON but different line-ending serialization. This is accepted as non-substantive formatting drift only. V2 must record the current V1R3 byte hash as its starting baseline and must not silently modify protected artifacts except for explicitly authorized new V2 Evidence outputs.

## Mandatory unresolved preflight check

The V1R3 Git report references changed helper scripts under `tools/` that were not included in the external review ZIP. Before V2 makes any implementation change, it must statically inspect all related controller/completion/review helper scripts and stop as BLOCKED if any path can bypass the approved controller state machine.

## Authorized execution

Execute only:

`V2_COST_STRESS_AND_ROBUSTNESS_ENGINE`

## Authorized V2 activity

- Read existing, already-produced historical evidence artifacts.
- Inventory available source data for cost, turnover, return series and candidate-comparison analysis.
- Implement read-only Cost-Stress and Robustness evidence modules.
- Generate new versioned Evidence outputs under `control/evidence/`.
- Update the unified Evidence export only through the controlled Evidence export path.
- Execute targeted Unit Tests only.
- Produce a V2 report and external review ZIP.

## Prohibited

- V3 or later execution
- model training or recalculation
- historical backtest execution or validation-matrix execution
- M1 recalculation
- research, replay, shadow or paper jobs
- promotion or rollback
- any trading or broker activity
- EXE build or execution
- champion change
- any automation-flag enablement
- productive signal-weight or economic-model-parameter changes
- scheduled or background Codex automation
