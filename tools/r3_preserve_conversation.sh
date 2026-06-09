#!/usr/bin/env bash
# Gespräch lokal sichern — R3 weiter ohne Cursor.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
exec "$PY" "$ROOT/tools/ai_kernel.py" r3-preserve
