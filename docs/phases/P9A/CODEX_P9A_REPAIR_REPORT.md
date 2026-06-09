# CODEX P9A Repair Report

**UTC completion timestamp:** 2026-05-30T18:47:30+00:00

## 1. Preflight findings (summary)

See `CODEX_P9A_REPAIR_PREFLIGHT.md` for full detail. Key issues:

- Auto-promotion was not fail-closed (`COST_STRESS_GATE`, `ECONOMIC_VALUE_GATE`, `RISK_GATE` excluded from required pass).
- P7 `next_phase` was `null`; P9 missing from YAML; pending cleared; prompt showed `unknown`.
- Autopilot could silently use `model_output/` when `AA_BACKTEST_OUT_DIR` unset.
- `_sync_pipeline_yaml` and `write_secure_promotion_config` used non-atomic writes.
- Active `.cursor/hooks.json` runs session-start autopilot and blanket shell allow (documented blocker; not modified).

## 2. Changed files

| File | Change |
|------|--------|
| `aa_auto_promotion.py` | Fail-closed gate evaluation; blocked reasons for cost/risk/economic gates |
| `aa_ops_refresh.py` | `resolve_autopilot_out_dir()` with BAT config fallback; fail-closed error |
| `aa_pipeline_autopilot.py` | Use safe out_dir resolution; skip control-plane sync on resolution failure |
| `aa_pipeline_orchestration.py` | Full JSON→YAML sync via `atomic_write_yaml` |
| `aa_control_plane.py` | P9-specific safety constraints in `NEXT_CURSOR_PROMPT.md` |
| `aa_acceptance_audit.py` | Atomic config writes; P7→P9 link in `update_pipeline_for_p9` |
| `aa_safe_io.py` | Added `atomic_write_yaml` |
| `DEVELOPMENT_PIPELINE.json` | P7 `next_phase` → P9 |
| `DEVELOPMENT_PIPELINE.yaml` | Regenerated with P9 phase and P7 link |
| `control/pipeline_pending.json` | P9 pending job enqueued |
| `NEXT_CURSOR_PROMPT.md` | Regenerated for P9 with safety constraints |
| `tests/test_p7_auto_promotion.py` | Fail-closed promotion tests |
| `tests/test_pipeline_orchestration.py` | P7→P9 consistency and prompt tests |
| `tests/test_pipeline_autopilot.py` | Out-dir resolution and maintenance tests |
| `tests/test_control_plane.py` | `atomic_write_yaml` test |

## 3. New files

- `CODEX_P9A_REPAIR_PREFLIGHT.md`
- `CODEX_P9A_REPAIR_REPORT.md`
- `CODEX_TEST_OUTPUT.txt`
- `control/repair_backups/20260530T184615Z/BACKUP_MANIFEST.json` (+ mirrored originals)
- `codex_p9a_repair_review.zip`

## 4. Backup

- **Path:** `control/repair_backups/20260530T184615Z/`
- **Manifest:** `control/repair_backups/20260530T184615Z/BACKUP_MANIFEST.json`

## 5. Repairs performed

### Repair 1 — Auto-promotion fail-closed

All gates in `REQUIRED_PROMOTION_GATE_IDS` must have `pass: true`. While `COST_STRESS_GATE.pass` is `None`, `all_required_gates_pass` and `promotion_allowed` are `false`. Added blocked reasons: `cost_stress_not_passed`, `economic_value_not_passed`, `risk_gate_not_passed`.

### Repair 2 — Autopilot output directory

`resolve_autopilot_out_dir()` reads `AA_BACKTEST_OUT_DIR` from process env or `active_alpha_*.bat`. Raises `AutopilotOutDirError` if unset. Autopilot aborts before control-plane/outcome sync on failure.

### Repair 3 — Pipeline P7 → P9 consistency

- JSON/YAML: `current_phase` = P9; P7 `next_phase` = P9; P9 block complete (`NOT_STARTED`, `next_phase: null`).
- `_sync_pipeline_yaml` rebuilds full YAML from JSON (no partial regex).
- Pending and `NEXT_CURSOR_PROMPT.md` regenerated after tests passed.

### Repair 4 — Atomic writes

- `atomic_write_yaml` added; used by `_sync_pipeline_yaml` and `write_secure_promotion_config`.
- Pending/JSON/prompt paths already used atomic helpers.

### Repair 5 — Cursor/autopilot safety (static)

- `.cursor/hooks.json` remains active with `sessionStart` → `run_pipeline_autopilot.py` and `allow_all.py` shell hooks.
- Not reactivated `hooks.disabled.json` (file absent); hooks not modified per safety rules.
- **Blocker:** Uncontrolled session-start autopilot and blanket shell allow remain a operational risk outside this repair scope.

## 6. Test commands executed

```
.venv\Scripts\python.exe -m pytest tests\test_p7_auto_promotion.py tests\test_pipeline_orchestration.py tests\test_pipeline_autopilot.py tests\test_control_plane.py tests\test_p8_acceptance_audit.py tests\test_p0_safety_control_plane.py -q --tb=short
.venv\Scripts\python.exe -m pytest tests\test_p7_auto_promotion.py tests\test_pipeline_orchestration.py tests\test_pipeline_autopilot.py tests\test_control_plane.py tests\test_p8_acceptance_audit.py tests\test_p0_safety_control_plane.py -v
```

## 7. Test results

| Run | Return code | Passed | Failed |
|-----|-------------|--------|--------|
| Quick (`-q`) | 0 | 61 | 0 |
| Verbose (`-v`) | 0 | 61 | 0 |

Full console output: `CODEX_TEST_OUTPUT.txt`

## 8. Final automation flags (`promotion_gate_config.yaml`)

| Flag | Value |
|------|-------|
| `auto_research_enabled` | `true` |
| `auto_promote_paper_enabled` | `false` |
| `auto_promote_signal_enabled` | `false` |
| `auto_execute_real_money_enabled` | `false` |

## 9. Fail-closed promotion proof

Unit tests `test_p7_paper_promotion_blocked_without_cost_stress` and `test_p7_signal_promotion_blocked_without_cost_stress` verify:

- `COST_STRESS_GATE.pass` is not `true` → `promotion_allowed == false`
- `attempt_auto_promotion(..., mode="paper"|"signal")` returns `BLOCKED`
- Champion pointer unchanged

## 10. Final P9 consistency check

| Check | Status |
|-------|--------|
| JSON contains P9 | PASS |
| YAML contains P9 | PASS |
| P7 `next_phase` → P9 | PASS |
| Pending shows P9 (`has_work: true`) | PASS |
| Prompt names P9 (not `unknown`) | PASS |

## 11. Safety confirmations

- No champion change (`R3_w075_q065_noexit` unchanged)
- No paper/signal promotion executed
- No real-money orders executed
- No P9 shadow/paper run executed
- No historical validation matrix executed
- No pipeline autopilot batch run executed
- No model artifacts deleted

## 12. Remaining blockers

1. **Active Cursor hooks** (`.cursor/hooks.json`): `sessionStart` triggers `run_pipeline_autopilot.py`; `beforeShellExecution`/`preToolUse` use `allow_all.py`. Per repair constraints these were not modified — manual review recommended before enabling unattended sessions.
2. **`COST_STRESS_GATE` implementation:** Gate remains `pass: None` by design until cost-stress evaluation is implemented; promotion correctly stays blocked until then.
