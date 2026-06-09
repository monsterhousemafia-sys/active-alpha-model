#!/usr/bin/env bash
# USB-Klon verabschieden — finaler Sync, Timer aus, Abschiedsbrief.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
USB_MOUNT="${1:-/run/media/machinax7/USB Stick}"

exec "$PY" -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT')
from analytics.usb_portable_farewell import farewell_usb_clone
doc = farewell_usb_clone(
    Path('$ROOT'),
    usb_mount='$USB_MOUNT',
    farewell_by_de='Operator',
    sync_before=True,
    persist=True,
)
print(doc.get('headline_de', ''))
for s in doc.get('steps') or []:
    print(' -', s.get('step'), 'OK' if s.get('ok') or s.get('skipped') else 'FAIL', s.get('detail_de', '')[:80])
print(doc.get('next_de', ''))
sys.exit(0 if doc.get('ok') else 1)
"
