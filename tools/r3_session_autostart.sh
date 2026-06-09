#!/usr/bin/env bash
# R3 OS — Login: Integritäts-Stack (Hub → Mirror → Qt). Getrennte Schichten.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  exit 0
fi

# Post-Login: Besitz + operative Unabhängigkeit (ohne Cursor)
bash "$ROOT/tools/r3_post_login_hook.sh" || true
"$PY" -c "
from pathlib import Path
from analytics.r3_operational_independence import scan_r3_operational_independence
from aa_safe_io import atomic_write_json
r = Path('$ROOT')
doc = scan_r3_operational_independence(r)
atomic_write_json(r / 'evidence/r3_operational_independence_latest.json', doc)
" >/dev/null 2>&1 || true

export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"
export AA_VISIBILITY_NOTIFY=1
export R3_SESSION=1
export R3_NATIVE_SHELL=1
export R3_SESSION_HUB_ONLY="${R3_SESSION_HUB_ONLY:-1}"
export AA_PRICE_DATA_SOURCE="${AA_PRICE_DATA_SOURCE:-internet}"

if [[ -f "$ROOT/control/preview_worker_join.json" ]]; then
  exec bash "$ROOT/tools/bootstrap_preview_federation.sh"
fi

"$PY" -c "
from pathlib import Path
from analytics.alpha_model_post_reboot_kill import run_post_reboot_kill_if_pending
run_post_reboot_kill_if_pending(Path('$ROOT'))
" >/dev/null 2>&1 || true

"$PY" "$ROOT/tools/ai_kernel.py" cognitive-kernel >/dev/null 2>&1 &
"$PY" -c "from pathlib import Path; from analytics.r3_os_supremacy import remove_ubuntu_background; remove_ubuntu_background()" >/dev/null 2>&1 || true

exec "$PY" -c "
from pathlib import Path
import json, sys

r = Path('$ROOT')

try:
    import threading
    from analytics.r3_desktop_view import run_r3_background_refresh
    threading.Thread(
        target=run_r3_background_refresh,
        args=(r,),
        name='r3-background-refresh',
        daemon=True,
    ).start()
except Exception:
    pass

try:
    from analytics.r3_browser_data import apply_session_browser_env, load_browser_data_policy
    pol = load_browser_data_policy(r)
    apply_session_browser_env(pol)
    if pol.get('session_autostart_ingest', True):
        import threading
        from analytics.r3_browser_data import ingest_prognosis_data_from_internet
        threading.Thread(
            target=ingest_prognosis_data_from_internet,
            kwargs={'force': False, 'fast': True, 'persist': True},
            name='r3-session-ingest',
            daemon=True,
        ).start()
except Exception:
    pass

try:
    from analytics.reboot_full_apply import complete_after_reboot, reboot_pending
    if reboot_pending(r):
        complete_after_reboot(r)
except Exception:
    pass

from analytics.stack_integrity import repair_stack

launch = __import__('os').environ.get('R3_SESSION_HUB_ONLY', '1') == '1'
doc = repair_stack(r, launch_cockpit_window=launch, persist=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('stack_ok') else 1)
"
