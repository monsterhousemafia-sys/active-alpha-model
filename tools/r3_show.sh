#!/usr/bin/env bash
# R3 OS — Status im Terminal.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1
echo "=== R3 — Research Operating System ==="
exec "$PY" "$ROOT/tools/ai_kernel.py" visibility
