#!/usr/bin/env bash
# R3 vom Cursor-Betrieb abnabeln — König + Bash + Autostart übernehmen.
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
from analytics.r3_operational_independence import apply_r3_operational_detach
import json, sys
doc = apply_r3_operational_detach(
    Path('$R3_ROOT'),
    repair=bool($REPAIR),
    seal_bridge=True,
    persist=True,
)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('operational_detach') else 1)
"
