#!/usr/bin/env bash
# Spread intensivieren — wie beim ersten erfolgreichen Bash-Lauf.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"

echo "[spread] Hub + Tunnel + Welt + Demand-Boost …"
"$PY" "$ROOT/tools/preview_hub.py" --ensure 2>/dev/null || true
"$PY" "$ROOT/tools/ai_kernel.py" spread-intensify
echo ""
echo "[spread] Community-Text:"
bash "$ROOT/tools/preview_spread.sh"
