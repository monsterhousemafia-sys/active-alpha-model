#!/usr/bin/env bash
# Vom Haus in die Welt — LAN bleibt, Tunnel + Welt-ZIP zusätzlich.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

export AA_PROJECT_ROOT="$R3_ROOT"
exec "$R3_PY" -c "
from pathlib import Path
from analytics.world_spread import activate_house_to_world
import json, sys

r = Path('$R3_ROOT')
doc = activate_house_to_world(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
