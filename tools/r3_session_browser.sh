#!/usr/bin/env bash
# R3 Browser — nur mit R3_ALLOW_BROWSER=1 (Standard: r3_cockpit.sh).
set -euo pipefail
if [[ "${R3_ALLOW_BROWSER:-0}" != "1" ]]; then
  echo "R3 läuft nur lokal (Qt). Start: bash tools/r3_cockpit.sh" >&2
  exit 1
fi
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1
export R3_SESSION=1

PATH_ARG="${1:-}"
if [[ -z "$PATH_ARG" ]]; then
  PATH_ARG="$("$PY" -c "
from pathlib import Path
from analytics.r3_session_browser import session_hub_path
print(session_hub_path(Path('$ROOT')))
")"
fi

exec "$PY" -c "
from pathlib import Path
from analytics.r3_session_browser import launch_session_cockpit
import json, sys
doc = launch_session_cockpit(Path('$ROOT'), hub_path=sys.argv[1])
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
" "$PATH_ARG"
