#!/usr/bin/env bash
# LAN/Festnetz-Verbreitung — gleicher Router (Telefonkabel/DSL/WLAN).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

VERIFY_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --verify) VERIFY_ONLY=1 ;;
  esac
done

export AA_PROJECT_ROOT="$R3_ROOT"
exec "$R3_PY" -c "
from pathlib import Path
from analytics.preview_federation import apply_lan_spread, verify_lan_spread
from analytics.community_spread_plan import broadcast_spread
import json, sys

r = Path('$R3_ROOT')
if $VERIFY_ONLY:
    doc = verify_lan_spread(r)
else:
    doc = apply_lan_spread(r)
    doc['verify'] = verify_lan_spread(r)
    if doc.get('ok'):
        doc['broadcast'] = broadcast_spread(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
