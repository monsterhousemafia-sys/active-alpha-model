#!/usr/bin/env bash
# R3 — Arbeitsfläche: eine Desktop-Funktion starten.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
FEATURE="${1:-}"
if [[ -z "$FEATURE" ]]; then
  echo "Nutzung: r3-shell-launch <feature-id>  (z.B. files, terminal, settings)"
  exit 2
fi
exec "$PY" -c "
from pathlib import Path
from analytics.r3_ubuntu_shell import launch_shell_feature
import json, sys
doc = launch_shell_feature(Path('$ROOT'), sys.argv[1])
print(json.dumps(doc, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
" "$FEATURE"
