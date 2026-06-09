#!/usr/bin/env bash
# Besitz ~/.local korrigieren (Cursor-Root-Sandbox) — manuell oder aus Install.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

export AA_PROJECT_ROOT="$R3_ROOT"
exec "$R3_PY" -c "
from pathlib import Path
from analytics.r3_home_ownership import fix_r3_home_ownership
import json, sys
doc = fix_r3_home_ownership(Path('$R3_ROOT'))
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
