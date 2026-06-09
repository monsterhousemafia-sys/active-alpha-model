# Public Git publish

## What was done locally

- Broken `.git` (missing `objects/`) was backed up to `.git.legacy-backup-*` and re-initialized on branch `main`.
- Initial public mirror commit created with governance source, tests, and docs.
- Secrets and machine-local runtime snapshots are excluded via `.gitignore`.
- Preflight scanner: `tools/publish_public_git_preflight.py`

## Publish to GitHub (operator)

```bash
# 1. Install git (once)
sudo apt install git gh

# 2. Authenticate GitHub CLI (browser or token)
gh auth login

# 3. Publish (creates public repo + push)
cd ~/active_alpha_model
bash tools/publish_public_git.sh
```

Or set an explicit remote:

```bash
export AA_PUBLIC_GIT_REMOTE='https://github.com/<USER>/active-alpha-model.git'
bash tools/publish_public_git.sh
```

## Re-run preflight only

```bash
.venv/bin/python3 tools/publish_public_git_preflight.py
```

Report (gitignored): `evidence/publish_public_git_preflight_latest.json`

## Safety

- Never commit `control/server.env`, `trading212_zugangsdaten.env`, or tunnel tokens.
- LAN / hostname / trycloudflare runtime evidence stays local (gitignored).
- `AA_PUBLISH_FORCE=1` bypasses preflight — use only after manual review.
