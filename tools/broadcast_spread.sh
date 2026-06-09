#!/usr/bin/env bash
# Verbreitung — Forum, WhatsApp, LAN + Internet (jeder soll es erfahren).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

export AA_PROJECT_ROOT="$R3_ROOT"
exec "$R3_PY" -c "
from pathlib import Path
from analytics.community_spread_plan import broadcast_spread, ensure_community_spread
import json, sys

r = Path('$R3_ROOT')
doc = broadcast_spread(r)
doc['sustain'] = ensure_community_spread(r, repair=True, persist=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
