#!/usr/bin/env bash
# Post-Login — Besitz ~/.local korrigieren (Cursor-Root-Sandbox), idempotent.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

export AA_PROJECT_ROOT="$R3_ROOT"
"$R3_PY" -c "
from pathlib import Path
from analytics.r3_home_ownership import run_post_login_hook
run_post_login_hook(Path('$R3_ROOT'))
" >/dev/null 2>&1 || true
