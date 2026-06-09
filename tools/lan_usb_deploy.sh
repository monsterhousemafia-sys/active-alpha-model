#!/usr/bin/env bash
# Effizienteste Haus-Verbreitung: ZIP auf USB oder per LAN — gleiches WLAN.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

ZIP="${AA_WORKER_ZIP:-$HOME/glasfaser_NOTFALL_worker_LITE.zip}"
[[ -f "$ZIP" ]] || ZIP="$HOME/active_alpha_worker_LITE.zip"

LAN_URL="$("$PY" -c "
import sys
sys.path.insert(0, '$ROOT')
from analytics.preview_federation import detect_lan_ip, federation_config
from pathlib import Path
r = Path('$ROOT')
cfg = federation_config(r)
port = int(cfg.get('hub_port') or 17890)
lan = detect_lan_ip()
if not lan:
    raise SystemExit('Keine LAN-IP')
url = f'http://{lan}:{port}'
if url.startswith('https://'):
    raise SystemExit('Haus-Deploy nur LAN-HTTP')
print(url)
" 2>/dev/null || echo "")"
[[ -n "$LAN_URL" ]] || { echo "[FEHLER] LAN-IP fehlt — king_ops lan-spread zuerst" >&2; exit 1; }

ANLEITUNG="$(mktemp)"
cat > "$ANLEITUNG" <<EOF
Active Alpha — Haus/LAN (effizienteste Variante)

Worker = jeder, der Rechenleistung bereitstellen kann (PC + Python 3).

1. ZIP entpacken
2. Doppelklick: Windows_START.bat  oder  ./Linux_START.sh
3. Gleiches WLAN/LAN wie König-PC (Router über Telefonkabel/DSL)

Join: ${LAN_URL}/join
Test: curl -fsS ${LAN_URL}/api/health

Nur Python 3 — kein Geld, kein Broker.
EOF

usage() {
  echo "Usage:"
  echo "  bash tools/lan_usb_deploy.sh --usb /media/USER/STICK"
  echo "  bash tools/lan_usb_deploy.sh --lan USER@192.168.x.x"
  echo "  bash tools/lan_usb_deploy.sh --show"
  echo ""
  echo "ZIP: $ZIP"
  echo "Join: ${LAN_URL}/join"
}

case "${1:-}" in
  --usb)
    DEST="${2:?USB-Mountpoint fehlt, z.B. /media/$USER/USBSTICK}"
    [[ -d "$DEST" ]] || { echo "[FEHLER] $DEST nicht gefunden" >&2; exit 1; }
    cp "$ZIP" "$DEST/active_alpha_worker_LITE.zip"
    cp "$ANLEITUNG" "$DEST/MITMACHEN.txt"
    sync
    echo "[OK] USB: $DEST"
    echo "     active_alpha_worker_LITE.zip"
    echo "     MITMACHEN.txt"
    ;;
  --lan)
    TARGET="${2:?Ziel fehlt, z.B. user@<lan-host>:~/}"
    scp "$ZIP" "$ANLEITUNG" "$TARGET"
    echo "[OK] LAN-Kopie nach $TARGET"
    echo "     Worker: unzip → Linux_START.sh / Windows_START.bat"
    ;;
  --show|""|help|-h)
    usage
    cat "$ANLEITUNG"
    ;;
  *)
    echo "[FEHLER] Unbekannt: $1" >&2
    usage >&2
    exit 1
    ;;
esac
rm -f "$ANLEITUNG"
