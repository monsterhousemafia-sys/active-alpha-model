# External Review Approval — V0R

Review decision: V0 is not yet approved for transition to V1.

Authorized phase:
- V0R_EXTERNAL_REVIEW_REMEDIATION only

Required remediations:
1. Make missing data-quality evidence fail-closed in auto-promotion gates.
2. Reject unsupported promotion modes fail-closed.
3. Refresh stale promotion status artifacts only after all automation flags are safe.
4. Verify that active Cursor session-start / blanket shell-allow hooks are disabled.
5. Package P9 implementation and status evidence for external review without executing P9.
6. Keep auto-research disabled during build-only development phases until separately approved.

Prohibited:
- V1 or later implementation
- any EXE build or execution
- any shadow, paper, research, replay, promotion, rollback, backtest, M1 or trading job
- any champion change
- any auto-promotion or real-money enablement

Reviewer decision: V1 remains blocked until V0R review passes.
