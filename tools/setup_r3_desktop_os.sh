#!/usr/bin/env bash
# R3 OS Desktop-Install — blockiert wenn Lokal-Apps PURGED (nur technische Exekutive).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"

"$PY" -c "
from pathlib import Path
from analytics.r3_desktop_os import install_desktop_os
import json, sys
doc = install_desktop_os(Path('$ROOT'))
print(json.dumps(doc, indent=2, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
