#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
"$PY" -c "
import json
from pathlib import Path
import sys
sys.path.insert(0, '$ROOT')
from analytics.remote_hub_access import install_remote_systemd_services
installed = install_remote_systemd_services(Path('$ROOT'))
print(json.dumps({'installed': installed}, indent=2))
"
