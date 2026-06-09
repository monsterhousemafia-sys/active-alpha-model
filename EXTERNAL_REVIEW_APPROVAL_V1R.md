# External Review Approval — V1R

Review date: 2026-05-30

## Reviewed artifact

- Artifact: `codex_v1_evidence_and_cascade_review.zip`
- Observed external SHA-256: `403c9a5c3660db6c6ae5b7d1582f6029add22b7fd2569c7c6e81dd997bb6d283`

## Review decision

V1 is not yet approved for transition to V2.

## Positive findings

- Evidence schema and initial experiment registry were created.
- Current candidate is capped at `BACKTESTED`.
- Automation flags remain disabled.
- Cursor hooks remain disabled.
- Follow-on phases were prepared only as templates.

## Required remediation

1. Enforce controller state-machine authorization against `automation_state.json`.
2. Block authorization when Champion evidence is missing or conflicting.
3. Block authorization when stored status artifacts show unsafe or conflicting promotion/real-money state.
4. Make the Evidence Aggregator strictly read-only.
5. Prevent `BACKTESTED` classification without verified provenance.
6. Make current configuration the primary source for automation-mode display and mark status disagreement as conflict.
7. Correct system-health interpretation.
8. Establish a real Git checkpoint.
9. Replace self-referential ZIP hashing with an external sidecar hash mechanism.
10. Add regression tests for every required remediation.

## Authorized execution

Execute only:

`V1R_EVIDENCE_AND_CONTROLLER_HARDENING`

## Prohibited

- V2 or later execution
- any research, replay, shadow, paper, promotion, rollback, backtest, M1 or trading job
- any EXE build or execution
- any champion change
- any automation-flag enablement
- any productive model parameter or signal-weight change
- any scheduled or background Codex automation
