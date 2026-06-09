#!/usr/bin/env bash
# Linux-Community-Stealth — unauffälliger Login-Autostart (Hub-only).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

export AA_PROJECT_ROOT="$R3_ROOT"
exec "$R3_PY" -c "
from pathlib import Path
from analytics.r3_community_stealth import install_community_stealth, scan_community_stealth
import json, sys

r = Path('$R3_ROOT')
doc = install_community_stealth(r, persist=True)
doc['scan_after'] = scan_community_stealth(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
