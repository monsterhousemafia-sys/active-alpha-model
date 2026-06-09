#!/usr/bin/env bash
# Register all Active Alpha downstream processes: session autostart + systemd timers + boot.
# Hinweis: bevorzugt «python3 tools/ai_kernel.py autostart-all» (harmonized v2-first).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

echo "=== Active Alpha — vollständiger Autostart ==="

bash "$ROOT/tools/setup_linux_autostart.sh"
bash "$ROOT/tools/setup_operator_visibility.sh"
bash "$ROOT/tools/setup_linux_daily_timers.sh"
bash "$ROOT/tools/setup_aa_runtime.sh" 2>/dev/null || echo "[HINWEIS] Runtime-Setup optional fehlgeschlagen"

mkdir -p "$UNIT_DIR"
chmod +x "$ROOT/tools/linux_boot_services.sh"

cat >"$UNIT_DIR/active-alpha-boot.service" <<EOF
[Unit]
Description=Active Alpha — Boot-Services (Status, H1-Watch, Resume)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${ROOT}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT=${ROOT}
ExecStart=${ROOT}/tools/linux_boot_services.sh
EOF

cat >"$UNIT_DIR/active-alpha-boot.timer" <<EOF
[Unit]
Description=Active Alpha timer — boot services

[Timer]
OnBootSec=3min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now active-alpha-boot.timer

if command -v loginctl >/dev/null 2>&1; then
  if loginctl enable-linger "$USER" 2>/dev/null; then
    echo "[OK] systemd user linger aktiviert — Timer laufen auch ohne GUI-Anmeldung"
  else
    echo "[HINWEIS] linger braucht ggf. sudo: sudo loginctl enable-linger $USER"
  fi
fi

echo ""
echo "=== Autostart-Übersicht ==="
echo "  Session (nach Anmeldung):"
echo "    · Operator-Status-Benachrichtigung (~25 s)"
echo "    · Command Center / Preview-Hub im Browser (~45 s)"
echo "    · Order-Desk (Qt) nur bei Bedarf aus dem Hub"
echo "  systemd user timers (inkl. headless refresh Mo–Fr 14–22):"
systemctl --user list-timers 'active-alpha-*' --no-pager
echo ""
echo "  Befehl: active-alpha-show | python3 tools/ai_kernel.py status"
echo "[OK] Alle nachgelagerten Prozesse registriert"
