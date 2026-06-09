#!/usr/bin/env bash
# NVMe einhängen + fstab (NTFS, Active Alpha Fast Data).
set -euo pipefail
PART="${AA_NVME_PART:-/dev/nvme0n1p1}"
MOUNT="${AA_NVME_MOUNT:-/mnt/active-alpha-nvme}"
UUID="${AA_NVME_UUID:-7C1A99BE1A9975BC}"
UIDN="${AA_NVME_UID:-$(id -u)}"
GIDN="${AA_NVME_GID:-$(id -g)}"
OPTS="uid=${UIDN},gid=${GIDN},windows_names,nofail"

if [[ $EUID -ne 0 ]]; then
  exec sudo env AA_NVME_PART="$PART" AA_NVME_MOUNT="$MOUNT" AA_NVME_UUID="$UUID" \
    AA_NVME_UID="$UIDN" AA_NVME_GID="$GIDN" "$0"
fi

command -v ntfs-3g >/dev/null || { echo "[FEHLER] ntfs-3g fehlt — apt install ntfs-3g" >&2; exit 1; }
mkdir -p "$MOUNT"
if ! mountpoint -q "$MOUNT"; then
  if ! mount -t ntfs-3g -o "$OPTS" "$PART" "$MOUNT" 2>/dev/null; then
    if command -v ntfsfix >/dev/null 2>&1; then
      echo "[INFO] NTFS reparieren (ntfsfix) …"
      ntfsfix -d "$PART" || true
      mount -t ntfs-3g -o "$OPTS" "$PART" "$MOUNT"
    else
      mount -t ntfs-3g -o "$OPTS" "$PART" "$MOUNT"
    fi
  fi
  echo "[OK] Gemountet: $PART → $MOUNT"
else
  echo "[OK] Bereits gemountet: $MOUNT"
fi

FSTAB_LINE="UUID=${UUID}  ${MOUNT}  ntfs-3g  ${OPTS}  0  0"
if ! grep -qF "$MOUNT" /etc/fstab 2>/dev/null; then
  echo "$FSTAB_LINE" >>/etc/fstab
  echo "[OK] fstab ergänzt"
else
  echo "[OK] fstab enthält bereits $MOUNT"
fi

DATA="${MOUNT}/active_alpha_fast_data"
mkdir -p "$DATA/shared_cache"
chown -R "${SUDO_USER:-$USER}:${SUDO_GID:-$GIDN}" "$MOUNT" 2>/dev/null || true
df -h "$MOUNT"
echo "[OK] NVMe bereit: $DATA"
