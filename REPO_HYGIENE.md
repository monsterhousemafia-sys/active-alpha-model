# Repository hygiene

Non-economic cleanup rules for this repo. **No signal, champion, or model-parameter changes.**

## Layout

| Path | Role |
|------|------|
| `docs/README.md` | **Documentation index** (phases, review, governance) |
| `docs/phases/<PHASE>/` | CODEX preflight/report/audit per phase |
| `docs/governance/` | G0/G1/matrix/risk-off cross-cutting reports |
| `docs/review/status/` | G0/G1/P9 external review status |
| `docs/review/sidecars/` | Review ZIP SHA256 sidecars |
| `docs/integrity/` | Protected hashes + session logs (regenerable) |
| `control/evidence/` | Authoritative read-only gate JSON for cockpit |
| `control/champion_lineage_policy.json` | Runtime champion lineage (R5 operational) |
| `evidence/archive/` | Regenerable build/test pipeline dumps (gitignored) |
| `build/decision_cockpit/work_*/` | PyInstaller work dirs (gitignored) |

Legacy basenames resolve via `aa_doc_paths.doc_path()`.

## Safe cleanup (allowed)

- Move regenerable logs/patches to `evidence/archive/<date>_<topic>/`
- Extend `.gitignore` for work dirs and local review ZIPs
- Refactor cockpit/authorization code without behavior change
- Commit logical groups (governance, hygiene, tests)

## Do not touch without external approval

- `promotion_gate_config.yaml` (protected hash scope)
- `control/operational_champion.json`, LKG, promotion pointers
- `model_output_sp500_pit_t212/` productive outputs
- `EXTERNAL_REVIEW_APPROVAL_*.md` (sealed)
- Re-run backtests or recompute gate evidence ad hoc

## Audit

```text
python tools/repo_hygiene_audit.py
python tools/repo_hygiene_refresh.py   # reset regenerable CODEX snapshots + governance exports
python tools/repo_cleanup_session.py   # archive loose root clutter + PyInstaller work dirs
```

## Smoke-test env vars (do not mix)

| Variable | Path |
|----------|------|
| `AA_DECISION_COCKPIT_SMOKE_TEST=1` | Legacy **readonly** V5R widget smoke → `evidence/v5r_exe_smoke_test_result.json` |
| `AA_INTERACTIVE_COCKPIT_SMOKE_TEST=1` | **Interactive** cockpit smoke → `evidence/p18_interactive_gui_smoke_test_result.json` |
| `AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST=1` | Full 16-check matrix → `evidence/interactive_cockpit_full_function_matrix.json` |

Never set legacy + full-function smoke in the same shell without clearing env first.

## Live market prices (cockpit)

| Variable | Default | Purpose |
|----------|---------|---------|
| `AA_LIVE_QUOTE_MAX_AGE_S` | `120` | Max quote age before calculations block |
| `AA_LIVE_QUOTE_REFRESH_INTERVAL_S` | `60` | Auto-refresh interval in GUI |
| `AA_OFFLINE_COCKPIT_TEST` | unset | Synthetic prices for CI only |

Module: `market/live_quote_engine.py` — snapshot at `paper/p16d/live_quote_snapshot.json`.

**Clean-tree target:** `git status` empty. **`promotion_gate_config.yaml`** must stay `MANUAL` with all `auto_*` flags `false` — revert any local override immediately.
