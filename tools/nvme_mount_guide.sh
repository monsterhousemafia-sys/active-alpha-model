#!/usr/bin/env bash
# NVMe für Active Alpha einhängen (einmalig, braucht sudo).
set -euo pipefail
PART="${AA_NVME_PART:-/dev/nvme0n1p1}"
MOUNT="${AA_NVME_MOUNT:-/mnt/active-alpha-nvme}"
DATA="${MOUNT}/active_alpha_fast_data"

echo "=== Active Alpha — NVMe Mount Guide ==="
echo "Partition: $PART"
echo "Ziel:      $MOUNT"
echo ""

if [[ ! -b "$PART" ]]; then
  echo "[FEHLER] Partition $PART nicht gefunden." >&2
  lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,MODEL | rg nvme || lsblk
  exit 1
fi

if mountpoint -q "$MOUNT" 2>/dev/null; then
  echo "[OK] Bereits eingehängt: $MOUNT"
  df -h "$MOUNT"
  exit 0
fi

echo "Schnell (ohne sudo, Desktop-Session):"
echo "  udisksctl mount -b /dev/nvme0n1p1"
echo "  bash tools/setup_nvme_storage.sh"
echo ""
echo "Dauerhaft unter /mnt (einmalig als Admin):"
echo ""
echo "  sudo mkdir -p $MOUNT"
echo "  sudo mount $PART $MOUNT"
echo "  sudo mkdir -p $DATA"
echo "  sudo chown -R \$USER:\$USER $MOUNT"
echo ""
echo "Dauerhaft in /etc/fstab (UUID ermitteln):"
echo "  sudo blkid $PART"
echo "  # Zeile z.B.:"
echo "  # UUID=XXXX  $MOUNT  ext4  defaults,nofail  0  2"
echo ""
echo "Danach im Projekt:"
echo "  bash tools/setup_nvme_storage.sh"
echo "  bash tools/cleanup_nvme_ballast.sh"
echo "  python3 tools/ai_kernel.py preview-hardware"
echo ""
echo "Dauerhaft (sudo, einmalig):"
echo "  bash tools/mount_nvme_active_alpha.sh"
echo ""
echo "Optional ext4 (nur ohne Windows D:):"
echo "  bash tools/prepare_nvme_ext4.sh"
echo ""
echo "[HINWEIS] Ohne NVMe laufen H1/validation_runs auf SATA — Preview funktioniert, aber langsamer."
