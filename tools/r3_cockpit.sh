#!/usr/bin/env bash
# R3 — lokales Qt-Cockpit (Abgleich + Integritäts-Stack, Vordergrund).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init
export R3_SESSION=1
export R3_NATIVE_SHELL=1

echo "R3 Cockpit — $(r3_hub_base_url)$(r3_surface_path)"
r3_print_upgrade_hint

exec "$R3_PY" -c "
from pathlib import Path
from analytics.stack_integrity import repair_stack
from analytics.r3_runtime import default_surface_path
import json, sys
doc = repair_stack(
    Path('$R3_ROOT'),
    surface_path=default_surface_path(Path('$R3_ROOT')),
    launch_cockpit_window=True,
    block=True,
    persist=True,
)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('stack_ok') else 1)
"
