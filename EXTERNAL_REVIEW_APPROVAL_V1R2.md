# External Review Approval — V1R2

Review date: 2026-05-30

## Reviewed artifact

- Artifact: `codex_v1r_evidence_controller_review.zip`
- Observed external SHA-256: `6033ad04a87a8cd7315743f73bc109461abe45be74f697c4efc75abbb92184b4`
- Sidecar verification: PASS

## Review decision

V1R is not yet approved for transition to V2.

## Confirmed positive findings

- Evidence aggregation is separated into read-only build and explicit export.
- Current candidate remains capped at BACKTESTED.
- Automation flags remain disabled.
- Cursor hooks remain disabled.
- Protected status artifacts included in both V1 and V1R review packages were unchanged.
- No operational phase was executed.

## Required remediation

1. Make the controller use the actual latest completed reviewed phase as predecessor, including remediation phases.
2. Add V1R and V1R2 to the auditable phase catalog and require V1R2 external sealing before V2 can be authorized.
3. Seal predecessor review hashes only from a later genuine external approval.
4. Treat incomplete or malformed safety-status artifacts as blocking.
5. Treat missing or incomplete automation configuration as UNKNOWN and blocking in Evidence output.
6. Ensure reports inside a review ZIP never claim that ZIP's final hash; they must use PENDING_EXTERNAL_SEAL.
7. Provide externally verifiable Git commit evidence.
8. Include compact provenance and champion-pointer artefacts in the next review package.

## Authorized execution

Execute only:

`V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING`

## Prohibited

- V2 or later execution
- any research, replay, shadow, paper, promotion, rollback, backtest, M1 or trading job
- any EXE build or execution
- any champion change
- any automation-flag enablement
- any productive model parameter or signal-weight change
- any scheduled or background Codex automation
