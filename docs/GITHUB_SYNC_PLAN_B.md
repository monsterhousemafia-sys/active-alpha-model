# GitHub sync — Plan B (browser upload, no token push)

Use when `publish_public_access.sh` fails (403/404) or system `git` is missing.

**Mirror:** https://github.com/monsterhousemafia-sys/active-alpha-model

## Steps

1. Log in as **monsterhousemafia-sys** on GitHub.
2. Open the target folder in the repo (or repo root).
3. **Add file → Upload files** → drag files from this machine.
4. Commit message example: `tools: publish helpers and share campaign assets`
5. **Commit directly to `main`**.

## Files to upload (local → GitHub path)

| Local path | GitHub path |
|------------|-------------|
| `docs/POST_CLIPBOARD.txt` | `docs/POST_CLIPBOARD.txt` |
| `docs/SHARE_TODAY_CHECKLIST.md` | `docs/SHARE_TODAY_CHECKLIST.md` |
| `docs/GITHUB_SYNC_PLAN_B.md` | `docs/GITHUB_SYNC_PLAN_B.md` |
| `tools/verify_github_push_token.py` | `tools/verify_github_push_token.py` |
| `tools/open_share_campaign.sh` | `tools/open_share_campaign.sh` |
| `tools/push_github_dulwich.py` | `tools/push_github_dulwich.py` |

Already on GitHub (verify): `docs/SHARE_KIT_EN.md`, main codebase from first publish.

## After upload

- Run share campaign: `bash tools/open_share_campaign.sh`
- Copy texts: `docs/POST_CLIPBOARD.txt`
- Optional: repo **About** → description + topics (see `SHARE_KIT_EN.md`)

## Token push (when fixed)

**Terminal-Eingabe geht nicht?** Token in **Cursor-Editor** speichern:

```bash
.venv/bin/python3 tools/setup_github_publish_token.py --editor
```

→ Datei `control/secrets/github_publish_token` öffnen, Token einfügen, speichern, dann:

```bash
bash tools/publish_public_access.sh
```

Classic PAT, scope **`repo`**, account **monsterhousemafia-sys**. Token **nie** in den Chat.
