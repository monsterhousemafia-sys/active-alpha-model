#!/usr/bin/env bash
# Jeder Ubuntu-Nutzer: zeigt was Auto tut und kann (ohne Dashboard).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1
exec "$PY" "$ROOT/tools/ai_kernel.py" visibility
