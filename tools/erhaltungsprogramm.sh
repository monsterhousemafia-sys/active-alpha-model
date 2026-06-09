#!/usr/bin/env bash
# Erhaltungsprogramm — Wartung + Bash-Welt-Konsolidierung.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

REPAIR=1
START=0
for arg in "$@"; do
  case "$arg" in
    --start) START=1; REPAIR=1 ;;
    --scan-only) REPAIR=0 ;;
    --repair) REPAIR=1 ;;
  esac
done

export AA_PROJECT_ROOT="$R3_ROOT"
exec "$R3_PY" -c "
from pathlib import Path
from analytics.erhaltungsprogramm import consolidate_bash_weltweit, start_erhaltungsprogramm
import json, sys

r = Path('$R3_ROOT')
if $REPAIR or $START:
    doc = start_erhaltungsprogramm(r, repair=bool($REPAIR), persist=True)
else:
    doc = consolidate_bash_weltweit(r, persist=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok', True) else 1)
"
