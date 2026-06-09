#!/usr/bin/env bash
# Glasfaser-Umzug — Community offline-sicher (3 Phasen).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

ACTION="scan"
REPAIR=0
for arg in "$@"; do
  case "$arg" in
    --init|--einleiten) ACTION="init" ;;
    --repair) REPAIR=1; ACTION="repair" ;;
    --go-offline) ACTION="go-offline" ;;
    --comeback) ACTION="comeback"; REPAIR=1 ;;
    --scan-only) ACTION="scan" ;;
    --cutover-now|--notfall|--bagger) ACTION="cutover" ;;
  esac
done

export AA_PROJECT_ROOT="$R3_ROOT"
exec "$R3_PY" -c "
from pathlib import Path
from analytics.glasfaser_offline_plan import (
    apply_glasfaser_cutover_now,
    apply_glasfaser_repair,
    initiate_glasfaser_plan,
    scan_glasfaser_offline,
    set_glasfaser_phase,
)
import json, sys

r = Path('$R3_ROOT')
action = '$ACTION'
if action == 'cutover':
    doc = apply_glasfaser_cutover_now(r, persist=True)
elif action == 'init':
    doc = initiate_glasfaser_plan(r, persist=True)
elif action == 'go-offline':
    doc = set_glasfaser_phase(r, phase_id='during_offline', ack=True, persist=True)
elif action == 'comeback':
    set_glasfaser_phase(r, phase_id='after_online', ack=True, persist=False)
    doc = apply_glasfaser_repair(r, persist=True) if $REPAIR else scan_glasfaser_offline(r, persist=True)
elif action == 'repair':
    doc = apply_glasfaser_repair(r, persist=True)
else:
    doc = scan_glasfaser_offline(r, persist=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
ok = bool(doc.get('ok'))
if action == 'init':
    ok = True
sys.exit(0 if ok else 1)
"
