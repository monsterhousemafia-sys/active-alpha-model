#!/usr/bin/env bash
# Einmalig: passwordloses sudo nur für NVMe-Mount (minimaler Scope).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
USER_NAME="${SUDO_USER:-${USER:-machinax7}}"
MOUNT_SCRIPT="$ROOT/tools/mount_nvme_active_alpha.sh"
SUDOERS="/etc/sudoers.d/active-alpha-nvme"
RULE="${USER_NAME} ALL=(ALL) NOPASSWD: ${MOUNT_SCRIPT}"

if [[ $EUID -ne 0 ]]; then
  exec sudo bash "$0"
fi

command -v ntfs-3g >/dev/null || apt-get install -y ntfs-3g

install -d -m 0750 /etc/sudoers.d
printf '%s\n' "$RULE" >"$SUDOERS"
chmod 0440 "$SUDOERS"
visudo -c -f "$SUDOERS"

echo "[OK] Passwordloses sudo für NVMe-Mount:"
echo "     $RULE"
echo ""
echo "Danach ohne Passwort:"
echo "  bash tools/king_ops.sh nvme"
echo "  bash tools/nvme_operator_setup.sh"
