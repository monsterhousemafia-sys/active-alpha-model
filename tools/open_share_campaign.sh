#!/usr/bin/env bash
# Open share campaign pages in browser (Reddit, HN, X, LinkedIn, GitHub repo).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_URL="https://github.com/monsterhousemafia-sys/active-alpha-model"

open_url() {
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1" >/dev/null 2>&1 &
  elif command -v sensible-browser >/dev/null 2>&1; then
    sensible-browser "$1" >/dev/null 2>&1 &
  else
    echo "OPEN: $1"
  fi
}

HN_TITLE="Show HN: Active Alpha – read-only quant decision cockpit with governance gates"
TWEET="Open-sourced Active Alpha: read-only Python decision cockpit for quant research — governance gates, fail-closed safety. ${REPO_URL} Not a trading bot. Not financial advice."

mapfile -t ENCODED < <("$ROOT/.venv/bin/python3" - <<'PY'
import urllib.parse
repo = "https://github.com/monsterhousemafia-sys/active-alpha-model"
title = "Show HN: Active Alpha – read-only quant decision cockpit with governance gates"
tweet = (
    "Open-sourced Active Alpha: read-only Python decision cockpit for quant research — "
    "governance gates, fail-closed safety. "
    + repo
    + " Not a trading bot. Not financial advice."
)
print(urllib.parse.quote(title, safe=""))
print(urllib.parse.quote(tweet, safe=""))
PY
)

echo "=== Share campaign — opening browser tabs ==="
echo "Repo: $REPO_URL"
echo "Texts: $ROOT/docs/POST_CLIPBOARD.txt"
echo ""

open_url "https://www.reddit.com/r/Python/submit"
sleep 1
open_url "https://news.ycombinator.com/submitlink?u=${REPO_URL}&t=${ENCODED[0]}"
sleep 1
open_url "https://twitter.com/intent/tweet?text=${ENCODED[1]}"
sleep 1
open_url "https://www.linkedin.com/sharing/share-offsite/?url=${REPO_URL}"
sleep 1
open_url "${REPO_URL}"
sleep 1
open_url "${REPO_URL}/settings"

echo ""
echo "Reddit: Title + Body from docs/POST_CLIPBOARD.txt"
echo "HN: add first comment from POST_CLIPBOARD.txt after submit"
echo "GitHub Settings: About + topics from POST_CLIPBOARD.txt"
