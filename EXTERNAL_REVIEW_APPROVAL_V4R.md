# External Review Approval — V4R

Review date: 2026-05-30

## Reviewed predecessor artifact

- Predecessor phase: `V4_DECISION_COCKPIT_GUI_INTEGRATION`
- Artifact: `codex_v4_gui_review.zip`
- Observed external SHA-256: `75808571c9cf44a2b58cc1dd85bff4d84640a4ccafd2bda61d09fd5622f28037`
- Sidecar verification: PASS

## Review decision

V4 is not yet approved for transition to V5.

## Confirmed positive findings

- Read-only Decision Cockpit modules and Qt integration exist.
- No new operative Cockpit action was identified.
- Hooks remain disabled.
- Automation flags remain disabled.
- Champion status artifacts continue to reference `R3_w075_q065_noexit`.
- Evidence Stage remains `BACKTESTED`.
- Monitoring remains blocked.
- V5 was not started.

## Required remediation

1. Remove fail-open Champion fallback in the GUI view model.
2. Make Evidence Stage and summaries source-validated and dynamic.
3. Display current blockers and source conflicts visibly in the GUI.
4. Read the experiment manifest using its actual schema fields.
5. Represent missing Monitoring evidence as UNKNOWN/BLOCKED FOR SAFETY rather than false certainty.
6. Restrict read-only export output to an isolated export directory outside protected paths.
7. Provide complete before/after protected-hash evidence.
8. Include complete Git status evidence in the review package.
9. Add tests for all repaired fail-closed paths.

## Authorized execution

Execute only:

`V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION`

## Prohibited

- V5 EXE build
- EXE execution
- V3S or V3P activation
- research, replay, market-data collection, shadow collection or paper simulation
- promotion, rollback, trading or broker connectivity
- champion change
- automation-flag enablement
- economic-model parameter or productive signal-weight changes
- scheduled or background Codex automation
