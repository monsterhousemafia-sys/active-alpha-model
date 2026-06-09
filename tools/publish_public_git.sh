#!/usr/bin/env bash
# Publish Active Alpha Model to a public Git host (GitHub).
# Repairs broken .git (missing objects/) by re-init when needed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPO_NAME="${AA_PUBLIC_GIT_REPO:-active-alpha-model}"
REMOTE_URL="${AA_PUBLIC_GIT_REMOTE:-}"
FORCE="${AA_PUBLISH_FORCE:-0}"
DRY_RUN="${AA_PUBLISH_DRY_RUN:-0}"

_git() {
  if command -v git >/dev/null 2>&1; then
    git "$@"
    return
  fi
  if [[ -x /tmp/git-portable/usr/bin/git ]]; then
    /tmp/git-portable/usr/bin/git "$@"
    return
  fi
  echo "git nicht gefunden. Installiere: sudo apt install git" >&2
  exit 1
}

_ensure_git() {
  if [[ -d .git/objects ]]; then
    return 0
  fi
  if [[ -d .git ]]; then
    backup=".git.legacy-backup-$(date -u +%Y%m%dT%H%M%SZ)"
    echo "WARN: .git/objects fehlt — sichere defektes Repo nach $backup"
    mv .git "$backup"
  fi
  _git init -b main
  _git config user.name "Active Alpha Publisher"
  _git config user.email "publisher@active-alpha.local"
}

_preflight() {
  "$ROOT/.venv/bin/python3" "$ROOT/tools/publish_public_git_preflight.py"
}

_stage_and_commit() {
  _git add -A
  if _git diff --cached --quiet; then
    echo "Nichts zu committen."
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN=1 — commit übersprungen."
    _git status -sb
    return 0
  fi
  _git commit -m "$(cat <<'EOF'
Publish public mirror: decision cockpit source and governance docs.

Research/read-only codebase with fail-closed safety gates; no secrets or local runtime snapshots.
EOF
)"
}

_push_remote() {
  if [[ -z "$REMOTE_URL" ]]; then
    if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
      echo "Erstelle öffentliches GitHub-Repo: $REPO_NAME"
      if [[ "$DRY_RUN" == "1" ]]; then
        echo "DRY_RUN=1 — gh repo create übersprungen."
        return 0
      fi
      gh repo create "$REPO_NAME" --public --source=. --remote=origin --push --description "Active Alpha / Marktanalyse Decision Cockpit (read-only, fail-closed)"
      return 0
    fi
    cat <<EOF

=== Manuell veröffentlichen ===
1. GitHub: neues öffentliches Repo "$REPO_NAME" anlegen (ohne README).
2. Remote setzen und pushen:
   git remote add origin https://github.com/<USER>/$REPO_NAME.git
   git push -u origin main

Optional mit gh (nach gh auth login):
   gh repo create $REPO_NAME --public --source=. --remote=origin --push

Preflight-Report: evidence/publish_public_git_preflight_latest.json
EOF
    return 0
  fi
  _git remote remove origin 2>/dev/null || true
  _git remote add origin "$REMOTE_URL"
  if [[ "$DRY_RUN" != "1" ]]; then
    _git push -u origin main
  fi
}

main() {
  _ensure_git
  set +e
  _preflight
  pf_exit=$?
  set -e
  if [[ $pf_exit -ne 0 && "$FORCE" != "1" ]]; then
    echo "Preflight fehlgeschlagen. .gitignore prüfen oder AA_PUBLISH_FORCE=1 setzen." >&2
    exit 2
  fi
  _stage_and_commit
  _push_remote
  echo "Fertig. Repository ist lokal committet; Remote siehe oben."
}

main "$@"
