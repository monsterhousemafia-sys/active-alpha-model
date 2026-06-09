#!/usr/bin/env bash
# WhatsApp-Spread — senden, prüfen, Einrichtung.
# Usage: bash tools/whatsapp_spread.sh <verify|send|send-brother|dry-run|enable> [args]
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/king_safe.sh
source "$(dirname "$_SELF")/king_safe.sh"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

CMD="${1:-verify}"
shift || true

export AA_PROJECT_ROOT="$R3_ROOT"
export AA_NO_LIVE_ORDER_SUBMISSION=1
export AA_EXECUTION_DRY_RUN=1

case "$CMD" in
  setup|install|einrichten)
    exec bash "$R3_ROOT/tools/setup_whatsapp_spread.sh" "$@"
    ;;
  auto-setup|auto-install|auto-auth)
    exec bash "$R3_ROOT/tools/setup_whatsapp_auto.sh" "${1:-check}" "${@:2}"
    ;;
  auto-check|auto)
    exec bash "$R3_ROOT/tools/setup_whatsapp_auto.sh" check
    ;;
  verify|check|status)
    exec "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_spread import verify_whatsapp_binding
from analytics.spread_shield import evaluate_spread_shield
import json, sys
r = Path('$R3_ROOT')
wa = verify_whatsapp_binding(r)
sh = evaluate_spread_shield(r, action='verify', dry_run=True)
doc = {'whatsapp': wa, 'shield': sh, 'ok': bool(wa.get('ok') and sh.get('ok'))}
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  shield|schott)
    exec "$R3_PY" -c "
from pathlib import Path
from analytics.spread_shield import evaluate_spread_shield
import json, sys
doc = evaluate_spread_shield(Path('$R3_ROOT'), action='verify', dry_run=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  dry-run|preview)
    PHONE="${1:-}"
    exec "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_spread import send_to_self, send_to_recipient
import json, sys
r = Path('$R3_ROOT')
doc = send_to_self(r, dry_run=True) if not '$PHONE' else send_to_recipient(r, phone='$PHONE', dry_run=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  durch|through|send-through)
    exec "$R3_PY" -c "
from pathlib import Path
from analytics.terminal_runtime import bootstrap_graphical_env
from analytics.whatsapp_spread import complete_self_send
import json, sys
bootstrap_graphical_env()
doc = complete_self_send(Path('$R3_ROOT'), dry_run=False)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('send_ok') else 1)
"
    ;;
  send-self|self|an-selbst|selbst)
    exec "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_spread import send_to_self
import json, sys
doc = send_to_self(Path('$R3_ROOT'), dry_run=False)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  send|senden)
    PHONE="${1:-}"
    NAME="${2:-}"
    exec "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_spread import send_to_self, send_to_recipient
import json, sys
r = Path('$R3_ROOT')
doc = send_to_self(r, dry_run=False) if not '$PHONE' else send_to_recipient(r, name='$NAME', phone='$PHONE', dry_run=False)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  send-brother|bruder|brother)
    echo "[INFO] send-brother → send-self (User schickt sich die Nachricht selbst)" >&2
    exec bash "$_SELF" send-self
    ;;
  enable)
    PROVIDER="${1:-waha}"
    exec "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_spread import enable_whatsapp
import json, sys
doc = enable_whatsapp(Path('$R3_ROOT'), provider='$PROVIDER')
print(json.dumps(doc, ensure_ascii=False, indent=2))
"
    ;;
  help|-h|--help|*)
    cat <<'EOF'
whatsapp_spread.sh — WhatsApp-Anbindung für Spread

  setup              WAHA Docker + Keyring (interaktiv)
  verify             Binding prüfen (fail-closed)
  dry-run [phone]    Vorschau (Standard: an dich selbst)
  shield|schott      Fail-closed Schott prüfen
  auto-setup         Playwright/xdotool einrichten (install|auth|check)
  durch              Auto-Send (xlib/xdotool, Text+ZIP) → Fallback manuell
  send-self          Spread an eigene Nummer (Weiterleitung manuell)
  send [phone]       Optional: direkt an andere Nummer
  enable [waha|green_api|callmebot|wa_me]

Provider:
  waha        Selbst gehostet (Text + ZIP) — empfohlen
  green_api   Cloud-API (Text + ZIP)
  callmebot   Nur Text (ZIP manuell)
  wa_me       Link öffnen (kein API-Versand)
EOF
    ;;
esac
