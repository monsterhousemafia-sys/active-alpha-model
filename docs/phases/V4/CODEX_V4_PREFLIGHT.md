# CODEX V4 Preflight — Read-Only GUI Integration

Generated: 2026-05-30 (UTC)

## V3 external seal

| Field | Value |
|-------|-------|
| Predecessor | `V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION` |
| Review ZIP | `codex_v3_monitor_foundation_review.zip` |
| Observed SHA-256 | `1a18b63ea3258d0761be168ee74e2093cb992a212aa5ee433ab3e4546886abb4` |
| Sidecar verification | PASS |

## Branch decision

- External approval selects **V4_DECISION_COCKPIT_GUI_INTEGRATION** only.
- **V3S_SHADOW_OBSERVATION_ACTIVATION** is explicitly not approved.

## V3 Git checkpoint

| Field | Value |
|-------|-------|
| Checkpoint commit | `12ec164d944e695aca0bcf08f2a9d68f4bc96197` |
| Branch | `codex/v3-forward-monitoring-foundation` |
| GIT_V3_CHECKPOINT_VERIFIED | YES |

## Hooks and safety

| Item | Value |
|------|-------|
| Hooks | DISABLED (empty `.cursor/hooks.json`) |
| Champion | `R3_w075_q065_noexit` |
| Evidence stage | BACKTESTED |
| Forward/Shadow/Paper monitoring | BLOCKED |

## Helper bypass audit

Module: `aa_v2_bypass_audit.py` — required before V4 run.

## V3 documentation correction

```text
V3_DOCUMENTATION_CORRECTION:
The V3 ZIP contains both baseline-cost backtest reports and the readiness status marks them present.
Cost Stress remains blocked independently because Challenger-specific turnover is not verified.
```

Local verification: both `backtest_report.txt` paths exist on disk.

## Planned GUI changes

- `aa_decision_cockpit_viewmodel.py` (new)
- `aa_decision_cockpit_gui.py` (new)
- `aa_decision_cockpit_export.py` (new)
- `aa_dashboard_qt_window.py` (read-only cockpit page)
- `aa_vision_controller.py` (branch selection for V4)

## Operational confirmation

No operative jobs, EXE build/execution, shadow/paper activation, or promotion.

Preflight result: **PASS**
