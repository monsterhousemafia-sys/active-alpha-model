#!/usr/bin/env bash
# Vollständiges Projekt auf USB — portable Kopie mit Pfad-Patch, Manifest und Verify
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

USB_MOUNT="${1:-/run/media/machinax7/USB Stick}"
DEST="$USB_MOUNT/active_alpha_model"
WITH_VENV="${AA_USB_WITH_VENV:-1}"

if [[ ! -d "$USB_MOUNT" ]]; then
  echo "[FEHLER] Mount nicht gefunden: $USB_MOUNT" >&2
  echo "Usage: bash tools/usb_full_project_deploy.sh [/media/USER/STICK]" >&2
  echo "       AA_USB_WITH_VENV=0 … ohne .venv (kleiner, pip beim ersten Start nötig)" >&2
  exit 1
fi

FREE_KB="$(df -Pk "$USB_MOUNT" | awk 'NR==2 {print $4}')"
NEED_KB="$(du -sk "$ROOT" | awk '{print $1}')"
if [[ "$WITH_VENV" == "0" ]]; then
  NEED_KB=$((NEED_KB - $(du -sk "$ROOT/.venv" 2>/dev/null | awk '{print $1}') || 0))
fi
if (( FREE_KB < NEED_KB + 500000 )); then
  echo "[FEHLER] Zu wenig Platz auf $USB_MOUNT (frei ${FREE_KB}K, Bedarf ~${NEED_KB}K)" >&2
  exit 1
fi

echo "[deploy] Pip-Freeze für USB-Wiederherstellung …"
mkdir -p "$ROOT/control"
"$PY" -m pip freeze > "$ROOT/control/usb_pip_freeze.txt"

echo "[deploy] Ziel: $DEST"
mkdir -p "$DEST"
RSYNC_EX=(
  --exclude '__pycache__/'
  --exclude '.pytest_cache/'
  --exclude 'active_alpha_worker_FULL/'
  --exclude '.Spotlight-V100/'
  --exclude '.fseventsd/'
  --exclude '._*'
  --exclude '*.sock'
  --exclude 'evidence/.runtime-api.sock'
  --exclude 'control/secrets/**/lock'
  --exclude 'robustness_results_trading212\_shared_cache/'
)
if [[ "$WITH_VENV" == "0" ]]; then
  RSYNC_EX+=(--exclude '.venv/')
  echo "[deploy] Ohne .venv — kleinere Kopie, USB_WEITERARBEITEN.sh baut venv neu."
fi

if ! rsync -aH --copy-links --info=progress2 "${RSYNC_EX[@]}" "$ROOT/" "$DEST/"; then
  echo "[WARN] rsync Exit ≠ 0 — meist harmlos (exFAT/Sockets/gebrochene Symlinks)." >&2
fi

chmod +x "$DEST/USB_WEITERARBEITEN.sh" 2>/dev/null || true

echo "[deploy] Pfade patchen, Manifest, Verify …"
FINALIZE="$("$PY" "$ROOT/tools/usb_portable_finalize.py" "$DEST" "$ROOT" "$USB_MOUNT" 2>&1)" || true
echo "$FINALIZE" | tail -20

if [[ "$WITH_VENV" == "0" ]]; then
  echo "[deploy] venv auf Stick neu bauen …"
  (cd "$DEST" && AA_PROJECT_ROOT="$DEST" bash ./USB_WEITERARBEITEN.sh --repair-only)
  "$PY" "$DEST/tools/usb_portable_finalize.py" --verify-only "$DEST" 2>&1 | tail -8 || true
fi

cat > "$USB_MOUNT/ACTIVE_ALPHA_USB_ANLEITUNG.txt" <<EOF
Active Alpha Model — USB-Kopie (verbessert)
===========================================
Ordner: active_alpha_model/
Stand: $(date -Iseconds)
Quelle: $ROOT

=== Erster Start (empfohlen, ein Befehl) ===
  cd "active_alpha_model"
  ./USB_WEITERARBEITEN.sh --full-setup

Das macht automatisch:
  • Spiegel nach ~/active_alpha_model (ext4, schnell)
  • venv prüfen/reparieren
  • Pfade in control/*.json anpassen
  • systemd-Timer (24/7 Prognose, Engine, t212-watch) neu installieren
  • king_ops Status + Verify

=== Nur vom Stick (ohne Install) ===
  ./USB_WEITERARBEITEN.sh

=== Hub / R3 ===
  .venv/bin/python tools/preview_hub.py --ensure
  http://127.0.0.1:17890/r3

=== Neuer PC ===
  T212-API-Keys neu im Keyring eintragen (liegen nicht auf dem Stick).

=== Erneut synchronisieren ===
  bash tools/usb_full_project_deploy.sh "$USB_MOUNT"

Manifest: active_alpha_model/control/usb_deploy_manifest.json
EOF

sync
echo "[OK] Deploy fertig: $DEST ($(du -sh "$DEST" | awk '{print $1}'))"
echo "     Anleitung: $USB_MOUNT/ACTIVE_ALPHA_USB_ANLEITUNG.txt"
echo "     Erster Start: cd \"$DEST\" && ./USB_WEITERARBEITEN.sh --full-setup"
