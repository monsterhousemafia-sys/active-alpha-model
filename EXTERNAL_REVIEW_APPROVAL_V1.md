# External Review Approval — V1

Review date: 2026-05-30

## Approved predecessor

V0R_EXTERNAL_REVIEW_REMEDIATION: APPROVED_FOR_V1

## Confirmed safety baseline

- Active Cursor session-start and blanket-shell-allow hooks were disabled in V0R.
- AUTO_RESEARCH is DISABLED.
- AUTO_PROMOTE_PAPER is DISABLED.
- AUTO_PROMOTE_SIGNAL is DISABLED.
- AUTO_EXECUTE_REAL_MONEY is DISABLED.
- Missing data-quality evidence blocks promotion fail-closed.
- Missing or non-passing cost-stress evidence blocks promotion fail-closed.
- Invalid promotion modes are blocked fail-closed.
- Champion remains R3_w075_q065_noexit.

## P9 classification

P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION remains classified as:

PREEXISTING_UNREVIEWED_PASS

P9 may be represented as existing preparation evidence only. It must not establish externally reviewed Shadow, Paper or Promotion eligibility.

## Authorized execution

Execute only:

V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION

## Authorized V1 output

V1 may implement:

- a versioned evidence schema,
- an experiment registry,
- a unified read-only evidence status export,
- a repositoryside gated controller for future phases,
- a phase catalog and approval templates,
- unit tests,
- reports and a review ZIP.

## Not authorized

- V2 or any later phase execution
- any EXE build or execution
- any operative research, replay, shadow, paper, promotion, rollback, backtest, M1 or trading job
- any champion change
- any automation flag enablement
- any economic model parameter or signal-weight change
- any scheduled or background Codex automation
