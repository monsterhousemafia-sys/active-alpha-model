#!/usr/bin/env bash
# Linux-Community-Ausbreitung sichern — Tunnel, ZIP, Forum, Timer.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

REPAIR=1
for arg in "$@"; do
  case "$arg" in
    --scan-only) REPAIR=0 ;;
    --repair) REPAIR=1 ;;
  esac
done

export AA_PROJECT_ROOT="$R3_ROOT"
exec "$R3_PY" -c "
from pathlib import Path
from analytics.community_spread_plan import ensure_community_spread, scan_community_spread
import json, sys

r = Path('$R3_ROOT')
if $REPAIR:
    doc = ensure_community_spread(r, repair=True, persist=True)
else:
    doc = scan_community_spread(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
