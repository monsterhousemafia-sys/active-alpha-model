#!/usr/bin/env bash
# Alles im Terminal — Install + Spread senden (ein Befehl).
# Usage: bash tools/whatsapp_terminal_all.sh [install|send|all]
set -euo pipefail
_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tools/r3_common.sh
source "$_ROOT/tools/r3_common.sh"
r3_init

export AA_PROJECT_ROOT="$R3_ROOT"
export AA_NO_LIVE_ORDER_SUBMISSION=1
export AA_EXECUTION_DRY_RUN=1

# Desktop-Session anbinden (Wayland/X11) — auch außerhalb des interaktiven Terminals.
eval "$("$R3_PY" -c "
from analytics.terminal_runtime import bootstrap_graphical_env, detect_runtime_context
import os
bootstrap_graphical_env()
for k in ('DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS'):
    v = os.environ.get(k,'')
    if v:
        print(f'export {k}='+repr(v))
")"

echo "=== Laufzeit ==="
"$R3_PY" -c "from analytics.terminal_runtime import emit_runtime_json; emit_runtime_json()"

CMD="${1:-all}"
shift || true

_install_system() {
  echo "=== [1/4] System-Pakete (sudo) ==="
  if command -v xclip >/dev/null 2>&1 && command -v xdotool >/dev/null 2>&1; then
    echo "[OK] xclip + xdotool bereits da"
    return 0
  fi
  if sudo -n true 2>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y xclip xdotool
    return 0
  fi
  if [ -t 0 ]; then
    echo "[sudo] Passwort eingeben für xclip + xdotool …"
    sudo apt-get update -qq
    sudo apt-get install -y xclip xdotool
    return 0
  fi
  echo "[SKIP] xclip/xdotool — kein interaktives sudo; weiter mit python-xlib/Firefox"
  return 0
}

_install_python() {
  echo "=== [2/4] Python-Deps + Firefox-Profil ==="
  "$R3_PY" -m pip install -q playwright pyautogui python-xlib
  bash "$_ROOT/tools/setup_whatsapp_auto.sh" profile
  bash "$_ROOT/tools/setup_whatsapp_auto.sh" install
}

_verify() {
  echo "=== [3/4] Schott + Capabilities ==="
  bash "$_ROOT/tools/whatsapp_spread.sh" shield
  bash "$_ROOT/tools/whatsapp_spread.sh" auto-check
}

_send() {
  echo "=== [4/4] Spread senden (durch) ==="
  "$R3_PY" -c "
from pathlib import Path
from analytics.terminal_runtime import detect_runtime_context, run_in_user_graphical_session
import json, sys
r = Path('$_ROOT')
ctx = detect_runtime_context()
if ctx.get('interactive_tty') and ctx.get('xdotool'):
    import subprocess
    proc = subprocess.run(['bash', str(r / 'tools/whatsapp_spread.sh'), 'durch'], cwd=str(r))
    raise SystemExit(proc.returncode)
res = run_in_user_graphical_session(['bash', 'tools/whatsapp_spread.sh', 'durch'], cwd=r, timeout_s=180.0)
print(json.dumps({'runtime': ctx, 'session_run': res}, ensure_ascii=False, indent=2))
if res.get('stdout'):
    print(res['stdout'])
if res.get('stderr'):
    print(res['stderr'], file=sys.stderr)
raise SystemExit(0 if res.get('ok') else 1)
"
}

_finish() {
  echo "=== Terminal-Aufgabe beenden ==="
  "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_terminal_finish import finish_terminal_task
import json, sys
doc = finish_terminal_task(Path('$_ROOT'))
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0)
"
}

case "$CMD" in
  finish|beenden|stop|ende|done)
    _finish
    ;;
  install|deps|setup)
    _install_system
    _install_python
    _verify
    echo ""
    echo "[FERTIG] Install OK — jetzt: bash tools/whatsapp_terminal_all.sh send"
    ;;
  send|durch|senden)
    _send
    ;;
  all|*)
    _install_system
    _install_python
    _verify
    _send
    ;;
esac
