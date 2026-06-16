#!/usr/bin/env bash
# Developer bootstrap — Stack stabil, Evidence, Smoke-Tests (keine Orders).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  export DISPLAY=:0
  export WAYLAND_DISPLAY=wayland-0
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
fi

echo "=== Developer Bootstrap ==="

bash "$ROOT/tools/project_security_lockdown.sh" | "$PY" -c "import json,sys; d=json.load(sys.stdin); print('Security:', d.get('headline_de',''))"

bash "$ROOT/tools/r3_ubuntu_stabilize.sh" | "$PY" -c "import json,sys; d=json.load(sys.stdin); print(d.get('headline_de',''))"

"$PY" -m pytest tests/test_p0_safety_control_plane.py tests/test_r3_ubuntu_stability.py -q

"$PY" -c "
from pathlib import Path
from datetime import datetime, timezone
import json
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root
from analytics.stack_integrity import build_integrity_report

root = Path('$ROOT')
trust = assess_t212_trust_from_root(root, persist=True)
stack = build_integrity_report(root, desktop_session=True)
doc = {
    'schema_version': 1,
    'released_for': 'developers',
    'updated_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    'stack_ok': stack.get('stack_ok'),
    'hub_port': stack.get('port'),
    'r3_cockpit': stack.get('r3', {}).get('cockpit_running'),
    't212_trusted': trust.get('trusted'),
    't212_reason_code': trust.get('reason_code'),
    't212_message_de': trust.get('message_de'),
    'headline_de': (
        'Developer-Release bereit — Stack OK'
        if stack.get('stack_ok')
        else 'Developer-Release — Stack prüfen'
    ),
    'commands_de': [
        'bash tools/r3_cockpit.sh',
        'bash tools/stack_integrity.sh --repair --launch',
        'docs/DEVELOPER_SETUP.md',
    ],
    'safety_de': 'Fail-closed — auto_execute und auto_promote bleiben aus',
}
atomic_write_json(root / 'evidence/developer_release_latest.json', doc)
print(json.dumps(doc, ensure_ascii=False, indent=2))
"

echo "[OK] evidence/developer_release_latest.json"
