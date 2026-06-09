#!/usr/bin/env bash
# Stack-Integrität — Hub + R3 prüfen und fail-closed reparieren.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1

REPAIR=0
LAUNCH=0
for arg in "$@"; do
  case "$arg" in
    --repair) REPAIR=1 ;;
    --launch) LAUNCH=1 ;;
  esac
done

exec "$PY" -c "
from pathlib import Path
from analytics.stack_integrity import build_integrity_report, repair_stack, verify_or_repair
import json, sys

root = Path('$ROOT')
repair = int('$REPAIR') == 1
launch = int('$LAUNCH') == 1

if repair:
    doc = repair_stack(root, launch_cockpit_window=launch, persist=True)
else:
    doc = verify_or_repair(root, auto_repair=True, launch_cockpit_window=launch, persist=True)

print(json.dumps({
    'stack_ok': doc.get('stack_ok'),
    'hub_ok': doc.get('hub_ok'),
    'r3_ok': doc.get('r3_ok'),
    'repaired': doc.get('repaired'),
    'failures_de': doc.get('failures_de'),
    'warnings_de': doc.get('warnings_de'),
    'evidence': 'evidence/stack_integrity_latest.json',
}, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('stack_ok') else 1)
"
