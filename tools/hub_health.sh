#!/usr/bin/env bash
# Preview-Hub Health — nur HTTP-Layer (ohne R3/Qt).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1

exec "$PY" -c "
from pathlib import Path
from analytics.hub_runtime import DEFAULT_PORT, build_health_report
from analytics.stack_integrity import ensure_hub_reliable
import sys

root = Path('$ROOT')
port = DEFAULT_PORT
try:
    port = ensure_hub_reliable(root, port=DEFAULT_PORT)
except Exception:
    pass
rep = build_health_report(root, port=int(port))
print('==============================================')
print(' Preview-Hub Health')
print('==============================================')
print(' Port:          ' + str(rep.get('port')))
print(' Online:        ' + ('JA' if rep.get('online') else 'NEIN'))
print(' /login:        ' + ('OK' if rep.get('route_login_ok') else 'FEHLER'))
print(' Schema:        v' + str(rep.get('hub_schema_version')))
print('----------------------------------------------')
print(' Start:         bash tools/hub_ensure.sh')
print(' Stop:          python3 tools/preview_hub.py --stop')
print('==============================================')
sys.exit(0 if rep.get('ok') else 1)
"
