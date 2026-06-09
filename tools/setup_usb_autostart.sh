#!/usr/bin/env bash
# systemd user timer — USB erkannt → install-local + Spread
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
INSTALL_DEST="${AA_USB_INSTALL_DEST:-$HOME/active_alpha_model}"
RUN_ROOT="$INSTALL_DEST"
if [[ ! -f "$RUN_ROOT/tools/king_ops.sh" ]]; then
  RUN_ROOT="$ROOT"
fi
WATCHER="$RUN_ROOT/tools/usb_auto_install_local.sh"
chmod +x "$WATCHER" 2>/dev/null || true

mkdir -p "$UNIT_DIR"
cat >"$UNIT_DIR/active-alpha-usb-autostart.service" <<EOF
[Unit]
Description=Active Alpha — USB auto install-local + Spread
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${RUN_ROOT}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT=${RUN_ROOT}
Environment=AA_USB_INSTALL_DEST=${INSTALL_DEST}
ExecStart=/bin/bash ${WATCHER}
EOF

cat >"$UNIT_DIR/active-alpha-usb-autostart.timer" <<EOF
[Unit]
Description=Active Alpha timer — USB auto install-local (alle 3 min)

[Timer]
OnBootSec=90
OnUnitActiveSec=3min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now active-alpha-usb-autostart.timer

echo "[OK] USB-Autostart: active-alpha-usb-autostart.timer (alle 3 min)"
echo "     Ziel: ${INSTALL_DEST}"
echo "     Policy: control/usb_portable_autostart.json"
echo "     Manuell: bash tools/usb_auto_install_local.sh"
systemctl --user list-timers 'active-alpha-usb-autostart.timer' --no-pager
