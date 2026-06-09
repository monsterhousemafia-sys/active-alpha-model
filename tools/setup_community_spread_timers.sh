#!/usr/bin/env bash
# systemd user timers — aus control/COMMUNITY_SPREAD_PLAN.json
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"
"$PY" -c "
from pathlib import Path
from analytics.community_spread_plan import sync_spread_timers
for line in sync_spread_timers(Path('$ROOT')):
    print('[OK]', line)
"
systemctl --user list-timers 'active-alpha-spread-tick-*' --no-pager 2>/dev/null || true
