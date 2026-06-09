# CODEX V1 Evidence and Cascade Report

UTC timestamp: 2026-05-30T19:40:00+00:00

## 1. Git and hook preconditions

- Git 2.54.0 available via full path
- Branch: `codex/v1-evidence-and-gated-cascade`
- Hooks: empty `.cursor/hooks.json`

## 2. Safety baseline

- Champion: `R3_w075_q065_noexit` (unchanged)
- All four automation flags: `false`
- P9: `PREEXISTING_UNREVIEWED_PASS`

## 3. Backup

- Path: `control/repair_backups/20260530T193650Z_V1/`
- Manifest: `BACKUP_MANIFEST.json` (AGENTS.md, VISION_PROGRESS.json)

## 4. Branch / commit status

- No commits; see `CODEX_V1_GIT_STATUS.txt`

## 5. Changed and new files

### New Python modules

- `aa_evidence_schema.py` — stages, classifications, fail-closed rules
- `aa_experiment_registry.py` — atomic experiment manifests
- `aa_evidence_status.py` — read-only unified evidence export
- `aa_vision_phase_catalog.py` — phase catalog loader
- `aa_vision_review_gate.py` — external approval validation
- `aa_vision_controller.py` — gated cascade controller (no job execution)

### New control structure

- `control/evidence/current_evidence_status.json`
- `control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml`
- `control/vision_automation/` (automation_state, cascade_policy, phase_catalog, transition_log, review_registry, templates, authorized_tasks)

### Updated

- `AGENTS.md` — global safety invariants and phase execution rules
- `VISION_PROGRESS.json` — `V1_EXTERNAL_REVIEW_REQUIRED`

### Tests

- `tests/test_evidence_schema.py`
- `tests/test_experiment_registry.py`
- `tests/test_evidence_status.py`
- `tests/test_vision_phase_catalog.py`
- `tests/test_vision_review_gate.py`
- `tests/test_vision_controller.py`

## 6. Evidence schema and fail-closed rules

Stages: IDEA, BACKTESTED, ROBUSTNESS_CHECKED, SHADOW_RUNNING, SHADOW_PASSED, PAPER_RUNNING, PAPER_CANDIDATE, REJECTED

Source classifications: NOT_AVAILABLE, HISTORICAL_EXISTING, PREEXISTING_UNREVIEWED, EXTERNALLY_REVIEWED, FORWARD_EXTERNALLY_APPROVED, STALE_OR_CONFLICTING

Fail-closed: missing cost/economic/risk/data-quality evidence caps at BACKTESTED; P9 unreviewed caps at BACKTESTED; source conflicts cap at BACKTESTED; no promotion/paper/real-money eligibility from aggregation code.

## 7. Experiment manifest MOM_63_TOP12

- ID: `EXP_INITIAL_MOM_63_TOP12`
- Stage: BACKTESTED
- Eligibility: all false
- Blockers: COST_STRESS_NOT_EVALUATED, P9_NOT_EXTERNALLY_REVIEWED

## 8. Unified evidence status

- Stage: BACKTESTED
- Classification: PREEXISTING_UNREVIEWED
- Blockers: COST_STRESS_NOT_EVALUATED, P9_NOT_EXTERNALLY_REVIEWED, ECONOMIC_VALUE_GATE conflict

## 9. Raw status source handling

- `auto_promotion_status.json` = promotion-safety source
- `promotion_status.json` = informative secondary view
- Conflicts recorded in `source_conflicts`; never elevate stage

## 10. Cascade structure

- Controller policy: FAIL_CLOSED_EXTERNAL_REVIEW_GATED
- automation_state execution_status: AWAITING_EXTERNAL_REVIEW
- authorized_phase: empty

## 11. Catalogued follow-on phases

V2, V3, V3S, V3P, V4, V5, COMPLETE_AWAITING_OPERATIONAL_DECISION — templates only; no execution.

## 12. No follow-on phase executed

Confirmed: V2+ not started; no real EXTERNAL_REVIEW_APPROVAL_V2.md created.

## 13. Tests

```text
pytest tests/test_evidence_schema.py tests/test_experiment_registry.py tests/test_evidence_status.py tests/test_vision_phase_catalog.py tests/test_vision_review_gate.py tests/test_vision_controller.py tests/test_p7_auto_promotion.py tests/test_pipeline_orchestration.py tests/test_pipeline_autopilot.py tests/test_control_plane.py tests/test_p9_controlled_shadow_paper_validation.py -q
```

Result: **85 passed** (see CODEX_V1_TEST_OUTPUT.txt)

## 14. Protected artifact hashes

| File | Before | After |
|------|--------|-------|
| latest_validated_run.json | e5a821da… | unchanged |
| last_known_good_state.json | f67b37eb… | unchanged |
| promotion_gate_config.yaml | d4c73d78… | unchanged |
| auto_promotion_status.json | e2901234… | unchanged |
| promotion_status.json | 14b8f53f… | unchanged |
| DEVELOPMENT_PIPELINE.json | cdde6183… | unchanged |
| DEVELOPMENT_PIPELINE.yaml | 032b4286… | unchanged |
| p9_shadow_paper_prep_status.json | d47657dc… | unchanged |

## 15. Confirmations

- Champion unchanged: YES
- No promotion: YES
- No real money: YES
- No operative jobs: YES
- No backtest: YES
- No EXE build/execution: YES
- No background automation: YES
- V2 not authorized: YES

## 16. Remaining blockers

- COST_STRESS_NOT_EVALUATED
- P9_NOT_EXTERNALLY_REVIEWED
- EXTERNAL_REVIEW_APPROVAL_V2.md not present

## 17. V2 recommendation

After external review of this ZIP, create genuine `EXTERNAL_REVIEW_APPROVAL_V2.md` (not TEMPLATE_) authorizing read-only cost-stress and robustness evidence computation only.

## Optional Codex command protection

No projektlokale `.codex/` rule layer added; protection via AGENTS.md, controller prechecks, and human approval files.
