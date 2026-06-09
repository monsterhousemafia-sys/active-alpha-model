#!/usr/bin/env bash
# Preview-Hub — nur HTTP-Server :17890 (kein R3/Qt).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
exec "$PY" "$ROOT/tools/preview_hub.py" --ensure "$@"
