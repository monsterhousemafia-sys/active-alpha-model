#!/usr/bin/env bash
# WhatsApp-Spread einrichten — WAHA (Docker) oder Keyring-Credentials.
set -euo pipefail
_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tools/r3_common.sh
source "$_ROOT/tools/r3_common.sh"
r3_init

echo "=== WhatsApp-Spread Einrichtung ==="
echo "Projekt: $_ROOT"
echo ""

WAHA_PORT="${WAHA_PORT:-3000}"
WAHA_IMAGE="${WAHA_IMAGE:-devlikeapro/waha}"
WAHA_CONTAINER="${WAHA_CONTAINER:-active-alpha-waha}"

_have_docker() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

_start_waha() {
  if ! _have_docker; then
    echo "[INFO] Docker nicht verfügbar — WAHA manuell starten oder anderen Provider wählen."
    return 1
  fi
  if docker ps -a --format '{{.Names}}' | grep -qx "$WAHA_CONTAINER"; then
    if ! docker ps --format '{{.Names}}' | grep -qx "$WAHA_CONTAINER"; then
      echo "[WAHA] Starte Container $WAHA_CONTAINER …"
      docker start "$WAHA_CONTAINER" >/dev/null
    else
      echo "[WAHA] Container läuft bereits."
    fi
  else
    echo "[WAHA] Erstelle Container auf Port $WAHA_PORT …"
    docker run -d --name "$WAHA_CONTAINER" -p "${WAHA_PORT}:3000" "$WAHA_IMAGE" >/dev/null
  fi
  echo "[WAHA] API: http://127.0.0.1:${WAHA_PORT}"
  echo "[WAHA] QR scannen:"
  echo "       1. Browser: http://127.0.0.1:${WAHA_PORT} (Dashboard)"
  echo "       2. Oder: curl -o /tmp/waha-qr.png http://127.0.0.1:${WAHA_PORT}/api/default/auth/qr"
  echo "       WhatsApp → Verknüpfte Geräte → QR scannen"
  return 0
}

_store_keyring() {
  local name="$1"
  local prompt="$2"
  echo ""
  read -r -p "$prompt: " -s value
  echo ""
  if [[ -z "$value" ]]; then
    echo "[SKIP] $name leer"
    return 1
  fi
  WAHA_SPREAD_SECRET="$value" "$R3_PY" -c "
import os
from pathlib import Path
from analytics.secure_credential_portal import keyring_set, keyring_available
r = Path('$_ROOT')
if not keyring_available():
    raise SystemExit('Keyring nicht verfügbar — pip install keyring SecretStorage')
ok = keyring_set(r, '$name', os.environ.get('WAHA_SPREAD_SECRET', ''))
raise SystemExit(0 if ok else 1)
" && echo "[OK] Keyring: $name gespeichert"
}

echo "Provider wählen:"
echo "  1) waha       — selbst gehostet, Text + ZIP (empfohlen)"
echo "  2) green_api  — Cloud, Text + ZIP"
echo "  3) callmebot  — nur Text"
echo "  4) wa_me      — nur Link öffnen"
read -r -p "Nummer [1]: " choice
choice="${choice:-1}"

provider="waha"
case "$choice" in
  2) provider="green_api" ;;
  3) provider="callmebot" ;;
  4) provider="wa_me" ;;
  *) provider="waha" ;;
esac

if [[ "$provider" == "waha" ]]; then
  _start_waha || true
  _store_keyring "waha_api_key" "WAHA API-Key (leer wenn keiner gesetzt)" || true
elif [[ "$provider" == "green_api" ]]; then
  _store_keyring "green_api_instance_id" "Green-API Instance ID"
  _store_keyring "green_api_token" "Green-API Token"
elif [[ "$provider" == "callmebot" ]]; then
  echo "CallMeBot: WhatsApp +49 34 6721 5728 → 'I allow callmebot to send me messages'"
  echo "API-Key kommt per WhatsApp zurück."
  _store_keyring "callmebot_api_key" "CallMeBot API-Key"
fi

"$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_spread import enable_whatsapp
enable_whatsapp(Path('$_ROOT'), provider='$provider')
print('[OK] control/whatsapp_spread.json → enabled=true, provider=$provider')
"

echo ""
echo "Prüfen:"
bash "$_ROOT/tools/whatsapp_spread.sh" verify || true
echo ""
read -r -p "Eigene WhatsApp-Nummer (E.164, z.B. 4915756402383): " self_phone
if [[ -n "$self_phone" ]]; then
  "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_spread import load_whatsapp_config, normalize_phone_e164
from aa_safe_io import atomic_write_json
r = Path('$_ROOT')
cfg = load_whatsapp_config(r)
cfg['send_mode'] = 'self'
cfg['self_phone_e164'] = normalize_phone_e164('$self_phone')
atomic_write_json(r / 'control/whatsapp_spread.json', cfg)
print('[OK] self_phone_e164 gesetzt')
"
fi

echo ""
echo "Test (ohne Versand): bash tools/king_ops.sh whatsapp dry-run"
echo "An dich selbst:      bash tools/king_ops.sh whatsapp send-self"
