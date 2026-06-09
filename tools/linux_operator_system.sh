#!/usr/bin/env bash
# Level D — system ops (requires --approve and user-granted scope D).
set -euo pipefail
ACTION="${1:-}"
APPROVE="${AA_OPERATOR_APPROVE_D:-}"

case "$ACTION" in
  nvme)
    cd "$(dirname "$0")/.."
    exec bash tools/nvme_operator_once.sh
    ;;
esac

if [[ "${APPROVE}" != "1" && "${2:-}" != "--approve" ]]; then
  echo "[FEHLER] Level D braucht Freigabe: AA_OPERATOR_APPROVE_D=1 oder --approve" >&2
  exit 2
fi

case "$ACTION" in
  apt)
    echo "[D] apt — Projekt-Abhängigkeiten …"
    sudo apt-get update -qq
    sudo apt-get install -y python3.14-venv python3-pip libxcb-cursor0 wget 2>/dev/null \
      || sudo apt-get install -y python3-venv python3-pip libxcb-cursor0 wget
    ;;
  remove-cursor)
    echo "[D] Cursor-Paket entfernen …"
    if command -v dpkg >/dev/null 2>&1 && dpkg -l cursor 2>/dev/null | grep -q '^ii'; then
      sudo -n apt-get remove -y cursor 2>/dev/null || sudo apt-get remove -y cursor
    else
      echo "[D] cursor nicht als deb-Paket installiert"
    fi
    ;;
  reboot)
    echo "[D] reboot in 5s — Ctrl+C zum Abbrechen"
    sleep 5
    if command -v loginctl >/dev/null 2>&1 && loginctl reboot 2>/dev/null; then
      exit 0
    fi
    if command -v systemctl >/dev/null 2>&1 && systemctl reboot 2>/dev/null; then
      exit 0
    fi
    sudo reboot
    ;;
  status)
    echo "[D] system status"
    uname -a
    systemctl --user list-timers 'active-alpha-*' --no-pager 2>/dev/null || true
    ls -la /run/media/"${USER:-machinax7}"/ 2>/dev/null || echo "NVMe: nicht eingehängt"
    ;;
  *)
    echo "Usage: AA_OPERATOR_APPROVE_D=1 bash tools/linux_operator_system.sh {apt|reboot|nvme|status} [--approve]" >&2
    exit 2
    ;;
esac
