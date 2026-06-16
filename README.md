# Active Alpha Model — Marktanalyse Decision Cockpit

Auditable, **read-only** decision cockpit for quantitative research: champion/challenger evidence, governance gates, pipeline status, and safety blockers.

## Public access (everyone)

**Browse or clone** the public mirror:

**https://github.com/monsterhousemafia-sys/active-alpha-model**

```bash
git clone https://github.com/monsterhousemafia-sys/active-alpha-model.git
```

No `git` installed? Use **Code → Download ZIP** on the GitHub page.

Full guide: **[docs/PUBLIC_ACCESS.md](docs/PUBLIC_ACCESS.md)** — what is included, safety rules, developer bootstrap.

Share / post templates (English): **[docs/SHARE_KIT_EN.md](docs/SHARE_KIT_EN.md)** · copy-paste: **[docs/POST_CLIPBOARD.txt](docs/POST_CLIPBOARD.txt)**

Maintainer publish (token with **repo** scope):

```bash
export GITHUB_TOKEN=ghp_...
.venv/bin/python3 tools/verify_github_push_token.py
bash tools/publish_public_access.sh
unset GITHUB_TOKEN
```

**Token push fails?** Browser upload: **[docs/GITHUB_SYNC_PLAN_B.md](docs/GITHUB_SYNC_PLAN_B.md)** · Share links: `bash tools/open_share_campaign.sh`

## Status

- **Pipeline:** `COMPLETE_AWAITING_OPERATIONAL_DECISION` — manual read-only only
- **Authoritative champion (review):** `R3_w075_q065_noexit` (see `EXTERNAL_REVIEW_APPROVAL_FINAL.md`)
- **Automation:** all `auto_*` flags remain **disabled** (fail-closed)

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for the current program state.

## Quick start (developers)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_active_alpha.txt
bash tools/developer_bootstrap.sh
```

See [docs/DEVELOPER_SETUP.md](docs/DEVELOPER_SETUP.md) (R3 desktop, T212 trust gate, safety).

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

Primary (token + dulwich, no system git):

```bash
export GITHUB_TOKEN='ghp_...'
.venv/bin/python3 tools/verify_github_push_token.py
bash tools/publish_public_access.sh
unset GITHUB_TOKEN
```

Plan B (browser upload): **[docs/GITHUB_SYNC_PLAN_B.md](docs/GITHUB_SYNC_PLAN_B.md)**

Preflight: `tools/publish_public_git_preflight.py` · manifest: `control/public_github_mirror.json`

## License

No license file is bundled. External use requires separate agreement; sealed review documents in the repository govern authorization boundaries.
