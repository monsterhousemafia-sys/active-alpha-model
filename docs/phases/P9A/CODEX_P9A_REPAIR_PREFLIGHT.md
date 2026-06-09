# CODEX P9A Repair Preflight

**UTC timestamp:** 2026-05-30T18:45:49+00:00

## Champion (unchanged)

- **Active champion:** `R3_w075_q065_noexit`
- **Validated run ID:** `20260530T153000Z_R3_w075_q065_noexit_d5eb43c3_b1143f32`
- **Source:** `control/last_known_good_state.json`, `model_output_sp500_pit_t212/latest_validated_run.json`

## Automation flags (before changes)

From `promotion_gate_config.yaml`:

| Flag | Value |
|------|-------|
| `auto_research_enabled` | `true` |
| `auto_promote_paper_enabled` | `false` |
| `auto_promote_signal_enabled` | `false` |
| `auto_execute_real_money_enabled` | `false` |

## Pipeline / pending / prompt state

| Source | Field | Value |
|--------|-------|-------|
| `DEVELOPMENT_PIPELINE.json` | `current_phase` | `P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION` |
| `DEVELOPMENT_PIPELINE.json` | P7 `next_phase` | **`null`** (should be P9) |
| `DEVELOPMENT_PIPELINE.json` | P9 phase | Present, `NOT_STARTED` |
| `DEVELOPMENT_PIPELINE.yaml` | `current_phase` | `P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION` |
| `DEVELOPMENT_PIPELINE.yaml` | P7 `next_phase` | **`null`** (should be P9) |
| `DEVELOPMENT_PIPELINE.yaml` | P9 phase | **Missing** |
| `control/pipeline_pending.json` | `has_work` | `false` (cleared; P9 not enqueued) |
| `NEXT_CURSOR_PROMPT.md` | current stage | **`unknown`** (stale/broken) |

## Detected inconsistencies

1. **Auto-promotion not fail-closed:** `aa_auto_promotion.py` omits `COST_STRESS_GATE`, `ECONOMIC_VALUE_GATE`, and `RISK_GATE` from `required_pass`. `COST_STRESS_GATE.pass` is `None`; promotion can still succeed when paper flag is enabled in tests.
2. **P7 → P9 pipeline drift:** JSON has P9 but P7 `next_phase` is `null` in both JSON and YAML; YAML lacks P9 phase block entirely. `_sync_pipeline_yaml` only regex-replaces status on existing phases.
3. **Autopilot output directory:** `resolve_out_dir()` silently defaults to `model_output/` when `AA_BACKTEST_OUT_DIR` is unset; project BAT config sets `model_output_sp500_pit_t212/`.
4. **Non-atomic YAML writes:** `_sync_pipeline_yaml` and `write_secure_promotion_config` use direct `write_text`.
5. **Pending/prompt out of sync:** P9 is current phase but pending cleared and prompt shows `unknown`.
6. **Cursor hooks (document only):** Active `.cursor/hooks.json` with `sessionStart` autopilot and `allow_all.py` shell hook — not modified per safety rules.

## Files expected to change

- `aa_auto_promotion.py`
- `aa_ops_refresh.py`
- `aa_pipeline_autopilot.py`
- `aa_pipeline_orchestration.py`
- `aa_control_plane.py`
- `aa_acceptance_audit.py`
- `aa_safe_io.py`
- `DEVELOPMENT_PIPELINE.json`
- `DEVELOPMENT_PIPELINE.yaml`
- `control/pipeline_pending.json`
- `NEXT_CURSOR_PROMPT.md`
- `tests/test_p7_auto_promotion.py`
- `tests/test_pipeline_orchestration.py`
- `tests/test_pipeline_autopilot.py`
- Possibly `tests/test_control_plane.py`, `tests/test_p8_acceptance_audit.py`

## Preflight confirmation

- No pipeline autopilot runs started
- No paper/signal promotion executed
- No real-money orders executed
- No P9 shadow/paper runs executed
- No historical validation matrix, M1 recalculation, research, replay, or background validation jobs executed
- No productive model artifacts modified
- Champion pointer not changed
