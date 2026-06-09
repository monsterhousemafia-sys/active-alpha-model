#!/usr/bin/env bash
# Cloudflared für Remote-Worker (König-PC only) — Worker braucht kein VPN.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/tools/bin"
mkdir -p "$BIN"
TARGET="$BIN/cloudflared"

if [[ -x "$TARGET" ]]; then
  echo "[OK] cloudflared bereits: $TARGET"
  "$TARGET" --version
  exit 0
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ASSET="cloudflared-linux-amd64" ;;
  aarch64|arm64) ASSET="cloudflared-linux-arm64" ;;
  *)
    echo "[FEHLER] Architektur $ARCH — manuell installieren: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" >&2
    exit 1
    ;;
esac

URL="https://github.com/cloudflare/cloudflared/releases/latest/download/${ASSET}"
echo "[install] Lade $URL …"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$URL" -o "$TARGET"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TARGET" "$URL"
else
  echo "[FEHLER] curl oder wget nötig" >&2
  exit 1
fi
chmod +x "$TARGET"
echo "[OK] $TARGET"
"$TARGET" --version
