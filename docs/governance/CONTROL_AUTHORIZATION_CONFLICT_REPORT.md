# Control Authorization Conflict Report — G0 Remediation

UTC inspection: 2026-05-31T18:53:23+00:00

Branch: `remediation/authorization-source-conflict`

HEAD before remediation commit: `6c13890cc3ca9e35d95f9215df761316fc99cb49`

## Sources read

- `EXTERNAL_REVIEW_APPROVAL_FINAL.md` — **authoritative**
- `V5R_EXTERNAL_ACCEPTANCE_REPORT.md`
- `VISION_PROGRESS.json`
- `DEVELOPMENT_PIPELINE.json` / `DEVELOPMENT_PIPELINE.yaml`
- `control/vision_automation/automation_state.json`
- `control/vision_automation/phase_catalog.json`
- `control/vision_automation/review_registry/review_registry.json`
- `control/operational_safety_flags.json`
- `control/system_health.json`, `control/last_known_good_state.json`
- `control/promotion_status.json`, `control/auto_promotion_status.json`
- `promotion_gate_config.yaml`
- `.cursor/hooks.json`

## Documented conflict

**Authoritative:** `EXTERNAL_REVIEW_APPROVAL_FINAL.md` approves V5R transition to `COMPLETE_AWAITING_OPERATIONAL_DECISION` for **manual read-only review only**. It explicitly states: *"No operational authorization is granted by this approval."*

**Conflicting (pre-remediation):**

- `VISION_PROGRESS.json` claimed `operational_authorization: FULL_USER_APPROVED` and safety flags (`REAL_MONEY_AUTHORIZED`, `PROMOTION_AUTHORIZED`, `PAPER_MONITORING_ACTIVATED`, `SHADOW_MONITORING_ACTIVATED`, `CHAMPION_CHANGE_AUTHORIZED`) all `YES`.
- `control/operational_safety_flags.json` had operational flags ENABLED/true.
- `control/vision_automation/automation_state.json` had `execution_status: OPERATIONAL_AUTHORIZED`, `operational_authorization: FULL_USER_APPROVED`, `real_money_execution_allowed: true`.

These claims must not be treated as valid operative authorization.

## Authoritative source rationale

External review approval is the sealed governance document for the V5R terminal state. Informational progress and automation state files may describe progress but **cannot authorize** Shadow, Paper, Promotion, Champion change, or Real-Money execution without registry-verified external seal and phase-catalog permission.

## Affected operative capabilities (blocked)

- Shadow monitoring activation
- Paper monitoring activation
- Promotion execution
- Champion change
- Real-money execution
- Operative jobs, backtest, replay, broker connectivity

## Fail-closed code changes

| File | Change |
|------|--------|
| `aa_authorization_policy.py` | Resolver; conflict detection; registry hash verification |
| `aa_decision_cockpit_viewmodel.py` | Authorization resolver integration; governance-blocked controller path |
| `aa_decision_cockpit_gui.py` | Authorization tab with blocked/conflict display |
| `aa_decision_cockpit_readonly_snapshot.py` | Terminal phase manual read-only only |
| `tests/test_authorization_conflict_fail_closed.py` | G0 fail-closed tests (10 cases) |
| `control/review_snapshot/v5r_decision_cockpit_snapshot.json` | Regenerated read-only manual-review snapshot |

## Remediated status files

| File | Remediation |
|------|-------------|
| `VISION_PROGRESS.json` | `operational_authorization: NONE`, `informational_only: true`, safety flags NO |
| `control/operational_safety_flags.json` | All automation/operational flags DISABLED |
| `control/vision_automation/automation_state.json` | Terminal read-only state; no operational authorization |

## New governance artefacts

- `control/authorization/authorization_source_policy.json`
- `control/authorization/current_authorization_status.json`
- `control/incidents/authorization_source_conflict_20260531T185323Z.json`

## Protected artefacts (unchanged)

All 14 paths in `CODEX_G0_PROTECTED_HASHES_BEFORE.json` match `CODEX_G0_PROTECTED_HASHES_AFTER.json` (0 hash differences).

Champion registry, evidence status, promotion config, and model output artefacts were **not** modified.

## Tests

```
pytest tests/test_authorization_conflict_fail_closed.py -q
pytest tests/test_decision_cockpit_viewmodel.py -q
pytest tests/test_decision_cockpit_gui.py -q
pytest tests/test_vision_phase_catalog.py -q
pytest tests/test_evidence_status.py -q
```

Result: **102 passed**, 0 failed (see `CODEX_G0_TEST_OUTPUT.txt`).

## Outcome

| Field | Value |
|-------|-------|
| Authorization Status | `MANUAL_READ_ONLY_ONLY` (post-remediation; conflicts cleared) |
| Operational Status | `BLOCKED_FOR_SAFETY` |
| G0 verdict | **PASS** |
| Operative use | **BLOCKED FOR SAFETY** |

No operative authorization exists. The terminal state permits only manual read-only review of the V5R EXE.

## Next step (external approval required)

`G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION` — see `EXTERNAL_REVIEW_APPROVAL_G1_TEMPLATE.md` and `NEXT_CURSOR_PROMPT.md`.

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL
