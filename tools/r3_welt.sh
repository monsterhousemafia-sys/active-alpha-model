#!/usr/bin/env bash
# R3 OS — Weltneuheit (/launch) mit Hub-Integrität.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"
export R3_SESSION=1

"$PY" "$ROOT/tools/ai_kernel.py" cognitive-kernel >/dev/null 2>&1 || true

if ! "$PY" -c "
from pathlib import Path
from analytics.linux_runtime_unified import kernel_is_authoritative
raise SystemExit(0 if kernel_is_authoritative(Path('$ROOT')) else 1)
"; then
  echo "[R3] Weltneuheit gesperrt — Cognitive Kernel v2 muss zuerst aktiv sein."
  echo "[R3] Daten: ~/.local/share/r3-os/"
fi

exec "$PY" -c "
from pathlib import Path
from analytics.stack_integrity import repair_stack
import json, sys
doc = repair_stack(Path('$ROOT'), surface_path='/launch', launch_cockpit_window=True, persist=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('stack_ok') else 1)
"
