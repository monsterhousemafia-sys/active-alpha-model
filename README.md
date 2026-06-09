# Active Alpha Model — Marktanalyse Decision Cockpit

Auditable, **read-only** decision cockpit for quantitative research: champion/challenger evidence, governance gates, pipeline status, and safety blockers.

## Status

- **Pipeline:** `COMPLETE_AWAITING_OPERATIONAL_DECISION` — manual read-only only
- **Authoritative champion (review):** `R3_w075_q065_noexit` (see `EXTERNAL_REVIEW_APPROVAL_FINAL.md`)
- **Automation:** all `auto_*` flags remain **disabled** (fail-closed)

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for the current program state.

## Quick start (developers)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_active_alpha.txt
.venv/bin/python -m pytest tests/test_p0_safety_control_plane.py -q
```

Windows-oriented launchers (`run_*.bat`) and PyInstaller build notes: [README_ACTIVE_ALPHA.md](README_ACTIVE_ALPHA.md), [OPS.md](OPS.md).

## Documentation

| Path | Purpose |
|------|---------|
| [docs/README.md](docs/README.md) | Documentation index |
| [AGENTS.md](AGENTS.md) | Agent / coding governance |
| [REPO_HYGIENE.md](REPO_HYGIENE.md) | Allowed vs forbidden edits |
| [VISION_DECISION_COCKPIT_EXECPLAN.md](VISION_DECISION_COCKPIT_EXECPLAN.md) | Program plan |

## Safety (public mirror)

This repository is a **research and governance** codebase:

- No real-money execution, broker orders, or automatic promotion
- No operative backtests or champion changes without external approval
- Secrets and local runtime snapshots are **gitignored** (`control/server.env`, spread operator evidence, archives)

Do not enable `auto_research_enabled`, `auto_promote_*`, or `auto_execute_real_money_enabled` without an explicit authorized phase.

## Publish / mirror

```bash
bash tools/publish_public_git.sh
```

Preflight report: `evidence/publish_public_git_preflight_latest.json`

Environment overrides:

- `AA_PUBLIC_GIT_REPO` — GitHub repo name (default: `active-alpha-model`)
- `AA_PUBLIC_GIT_REMOTE` — explicit remote URL to push
- `AA_PUBLISH_FORCE=1` — commit despite preflight warnings (not recommended)

## License

No license file is bundled. External use requires separate agreement; sealed review documents in the repository govern authorization boundaries.
