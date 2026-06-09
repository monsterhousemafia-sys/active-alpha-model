#!/usr/bin/env bash
# Operator-Segnung der USB-Portable-Kopie (fail-closed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
TARGET="${1:-$ROOT}"
NOTE="${2:-}"

exec "$PY" -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT')
from analytics.usb_portable_seal import bless_usb_portable_copy
doc = bless_usb_portable_copy(
    Path('$TARGET'),
    blessed_by_de='Operator',
    note_de='''$NOTE'''.strip() or '',
    persist=True,
)
print(doc.get('headline_de', ''))
print('status:', doc.get('status'))
print('project_root:', doc.get('project_root'))
if doc.get('verification', {}).get('blockers'):
    print('blockers:', doc['verification']['blockers'])
sys.exit(0 if doc.get('blessed') else 1)
"
