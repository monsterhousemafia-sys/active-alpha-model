#!/usr/bin/env bash
# systemd + Session-Autostart für Preview-Worker (idempotent).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
mkdir -p "$UNIT_DIR" "$AUTOSTART"

if [[ ! -f "$ROOT/control/preview_worker_join.json" ]]; then
  echo "[SKIP] Kein Worker-Bundle (preview_worker_join.json fehlt)"
  exit 0
fi

cat >"$UNIT_DIR/active-alpha-preview-worker.service" <<EOF
[Unit]
Description=Active Alpha — Preview Federation Worker
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT=${ROOT}
ExecStart=${PY} ${ROOT}/tools/preview_federation_worker.py --join-from-config --no-preview
Restart=on-failure
RestartSec=45

[Install]
WantedBy=default.target
EOF

cat >"$AUTOSTART/active-alpha-worker-bootstrap.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Active Alpha — Worker verbinden
Comment=Meldet Rechenleistung an das zentrale Preview Command Center
Exec=env AA_PROJECT_ROOT=${ROOT} ${ROOT}/tools/bootstrap_preview_federation.sh
Path=${ROOT}
Icon=chart-line
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=20
StartupNotify=false
EOF
chmod 644 "$AUTOSTART/active-alpha-worker-bootstrap.desktop"

systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable active-alpha-preview-worker.service 2>/dev/null || true

echo "[OK] Worker-Dienst: active-alpha-preview-worker.service"
echo "[OK] Autostart: $AUTOSTART/active-alpha-worker-bootstrap.desktop"
