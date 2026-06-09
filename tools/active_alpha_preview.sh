#!/usr/bin/env bash
# Active Alpha Preview — läuft Check + öffnet Apple-Style HTML im Browser.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"
exec "$PY" "$ROOT/tools/run_gui_preview.py" --open-html "$@"
