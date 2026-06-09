#!/usr/bin/env bash
# Alle R3-Lokal-Anwendungen vom System entfernen (Desktop, Menü, Autostart, ~/.local/bin).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
"$PY" -c "
from pathlib import Path
from analytics.r3_desktop_os import purge_r3_local_apps
import json
print(json.dumps(purge_r3_local_apps(Path('$ROOT')), indent=2, ensure_ascii=False))
"
