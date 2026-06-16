#!/usr/bin/env bash
# Ubuntu — R3 Desktop stabilisieren (Qt/Keyring/Wayland, Hub, Cockpit).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1
export R3_SESSION=1
export R3_NATIVE_SHELL=1
export R3_FULLSCREEN=0

# Grafische Sitzung
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  export DISPLAY=:0
  export WAYLAND_DISPLAY=wayland-0
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
fi

exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.r3_ubuntu_stability import stabilize_stack
import json, sys
doc = stabilize_stack(Path('$ROOT'), relaunch_cockpit=True, restart_hub=False)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('stack_ok') else 1)
"
