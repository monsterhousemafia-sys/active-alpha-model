# CODEX V4 GUI Integration Report

Phase: `V4_DECISION_COCKPIT_GUI_INTEGRATION`  
Generated: 2026-05-30 (UTC)

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL

## Summary

V4 integrated read-only Decision Cockpit views into the existing Qt dashboard. All evidence, monitoring, safety, and controller artifacts are loaded without writes to control paths.

## V3 external seal

| Field | Value |
|-------|-------|
| Sealed by | `EXTERNAL_REVIEW_APPROVAL_V4.md` |
| V3 ZIP SHA-256 | `1a18b63ea3258d0761be168ee74e2093cb992a212aa5ee433ab3e4546886abb4` |
| Branch selected | V4 (not V3S) |
| V3_EXTERNAL_SEALED | YES |

## V3 documentation correction

The V3 monitoring report incorrectly stated baseline-cost backtest reports were absent. The reviewed V3 ZIP and local tree contain both reports; `forward_monitoring_readiness_status.json` marks them present. **Cost Stress remains NOT_EVALUABLE** because Challenger-specific turnover is not verified.

## GUI deliverables

| Module | Purpose |
|--------|---------|
| `aa_decision_cockpit_viewmodel.py` | Fail-closed read-only data loader |
| `aa_decision_cockpit_gui.py` | Tabbed read-only cockpit widgets |
| `aa_decision_cockpit_export.py` | Optional JSON export to separate directory |
| `aa_dashboard_qt_window.py` | Cockpit page + Read-Only navigation button |

Mandatory views: Executive Overview, Safety, Evidence Ladder, Why Not Promoted, Cost/Robustness, Monitoring, Experiment, Audit Chain.

Banners: `NO LIVE TRADING`, `NO AUTO PROMOTION`, `READ-ONLY DECISION COCKPIT`.

No promotion, shadow, paper, trading, pipeline or EXE-build UI actions added.

## Controller state after V4

| Field | Value |
|-------|-------|
| current_executed_phase | V4_DECISION_COCKPIT_GUI_INTEGRATION |
| expected_next_phase | V5_WINDOWS_EXE_BUILD_AND_VERIFICATION |
| execution_status | AWAITING_EXTERNAL_REVIEW |
| next_phase_authorized | false |

V5 not started.

## Tests

181 regression tests passed (4 GUI tests skipped without display). Output: `CODEX_V4_TEST_OUTPUT.txt`.

## Protected artifacts

Pre/post SHA-256 in `CODEX_V4_PROTECTED_HASHES_*.json`. Monitoring and V2R evidence files unchanged.
