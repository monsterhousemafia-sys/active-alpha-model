#!/usr/bin/env bash
# Ubuntu: Launch-Fortschritt im Browser öffnen
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
"$PY" "$ROOT/tools/ai_kernel.py" launch-progress
