# Public access — clone and use (read-only mirror)

This repository is a **public read-only mirror** of the Active Alpha / Marktanalyse Decision Cockpit source and governance docs.

## Clone (anyone)

**Live mirror:** https://github.com/monsterhousemafia-sys/active-alpha-model

```bash
git clone https://github.com/monsterhousemafia-sys/active-alpha-model.git
cd active-alpha-model
```

Without system `git`, download **Code → Download ZIP** on GitHub.

## Quick start (developers)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_active_alpha.txt
bash tools/developer_bootstrap.sh
```

Details: [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md)

## What you get

| Included | Not in public mirror |
|----------|----------------------|
| Python source, tests, docs | `.env`, API keys, `control/secrets/` |
| Governance policies (`control/*.json`) | Local model parquet caches |
| Fail-closed safety flags (disabled automation) | Operator LAN/spread/tunnel runtime |
| R3 architecture docs | Large validation run outputs |

## What you must not do without authorization

- Enable `auto_execute_real_money_enabled`, `auto_promote_*`, or change the locked champion
- Run operative backtests or promotion jobs without sealed `EXTERNAL_REVIEW_APPROVAL_*.md`
- Commit secrets into a fork — use `.gitignore` patterns from this repo

## Publish updates (maintainer)

```bash
export GITHUB_TOKEN='ghp_...'
.venv/bin/python3 tools/verify_github_push_token.py
bash tools/publish_public_access.sh
unset GITHUB_TOKEN
```

Preflight: `tools/publish_public_git_preflight.py`

**403/404 on push?** Upload changed files in the browser: [GITHUB_SYNC_PLAN_B.md](GITHUB_SYNC_PLAN_B.md)

Share campaign: `bash tools/open_share_campaign.sh` · texts: [POST_CLIPBOARD.txt](POST_CLIPBOARD.txt)

## License

No license file is bundled. External use requires separate agreement; review documents in the repository define authorization boundaries.
