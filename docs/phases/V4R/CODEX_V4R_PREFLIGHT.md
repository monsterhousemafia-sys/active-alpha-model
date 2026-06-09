# CODEX V4R Preflight

Generated: 20260530T213403Z

## V4 external seal target

- Predecessor phase: `V4_DECISION_COCKPIT_GUI_INTEGRATION`
- Review ZIP: `codex_v4_gui_review.zip`
- Expected external SHA-256: `75808571c9cf44a2b58cc1dd85bff4d84640a4ccafd2bda61d09fd5622f28037`
- V4R seals V4 on `register_external_approval`

## Controller state (pre-V4R)

- current_executed_phase: `V4_DECISION_COCKPIT_GUI_INTEGRATION`
- expected_next_phase (reconciled to V4R): `V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION`
- execution_status: `AWAITING_EXTERNAL_REVIEW`

## Hook and safety status

- Hooks active: YES
- LOCKED_CHAMPION: R3_w075_q065_noexit
- Evidence stage: BACKTESTED (must not increase)
- V5 not started: YES

## Fail-closed GUI findings remediated in V4R

1. Champion fail-open fallback removed — multi-source consensus required
2. Evidence stage now source-validated and dynamic
3. Current blockers and source conflicts visible in GUI
4. Experiment manifest uses actual schema fields
5. Missing monitoring evidence shows UNKNOWN — BLOCKED FOR SAFETY
6. Export restricted to isolated directories outside protected paths
7. Complete before/after protected-hash evidence (V4 after file was incomplete)
8. Git status included in review package
9. Tests added for all fail-closed paths

## V4 protected hash note

- `CODEX_V4_PROTECTED_HASHES_AFTER.json` was incomplete (3 paths only)
- V4R generates full 16-path before/after sets

## Prohibited in this run

- V5 EXE build or execution
- Operative jobs, promotion, champion change
