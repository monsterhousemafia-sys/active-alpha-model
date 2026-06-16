#!/usr/bin/env bash
# Öffentlichen GitHub-Mirror veröffentlichen: Preflight → Commit → Push → Public-Settings
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "${GITHUB_TOKEN:-}" && -z "${GH_TOKEN:-}" ]]; then
  echo "GITHUB_TOKEN fehlt. Token: https://github.com/settings/tokens/new (Scope: repo)" >&2
  exit 2
fi

export AA_PUBLIC_GIT_PRIVATE="${AA_PUBLIC_GIT_PRIVATE:-0}"

echo "=== Preflight (Secrets/Leaks) ==="
if ! "$ROOT/.venv/bin/python3" "$ROOT/tools/publish_public_git_preflight.py"; then
  echo "Preflight BLOCK — Abbruch. Siehe Ausgabe oben." >&2
  exit 2
fi

echo "=== Lokale Änderungen committen ==="
"$ROOT/.venv/bin/python3" <<'PY'
from dulwich import porcelain
porcelain.add(".", paths=["."])
try:
    porcelain.commit(
        ".",
        message=b"Public access: README, docs, GitHub public mirror configuration.",
        author=b"Active Alpha Publisher <publisher@active-alpha.local>",
        committer=b"Active Alpha Publisher <publisher@active-alpha.local>",
    )
    print("Commit erstellt.")
except Exception:
    print("Nichts Neues zu committen.")
PY

echo "=== Push + öffentliche Repo-Einstellungen ==="
"$ROOT/.venv/bin/python3" "$ROOT/tools/push_github_dulwich.py"

echo ""
echo "Fertig. Link steht oben (Clone-URL). Token danach: unset GITHUB_TOKEN"
