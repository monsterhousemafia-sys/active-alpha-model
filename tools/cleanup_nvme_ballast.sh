#!/usr/bin/env bash
# Remove non-canonical duplicates on NVMe — keeps active_alpha_fast_data/.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY=".venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

mount="$("$PY" -c "
from pathlib import Path
from execution.linux_nvme_storage import resolve_nvme_mount
m = resolve_nvme_mount(Path('$ROOT'))
print(m or '')
")"

if [[ -z "$mount" ]]; then
  echo "[FEHLER] NVMe nicht eingehängt." >&2
  exit 1
fi

DATA="$mount/active_alpha_fast_data"
if [[ ! -d "$DATA" ]]; then
  echo "[FEHLER] $DATA fehlt — Abbruch." >&2
  exit 1
fi

echo "[INFO] NVMe: $mount"
echo "[INFO] Behalte: $DATA"

remove_path() {
  local rel="$1"
  local target="$mount/$rel"
  if [[ "$target" == "$DATA" || "$target" == "$DATA/"* ]]; then
    echo "[SKIP] geschützt: $rel"
    return 0
  fi
  if [[ ! -e "$target" ]]; then
    echo "[SKIP] fehlt: $rel"
    return 0
  fi
  local local_kb removed=0 failed=0
  local_kb=$(du -sk "$target" 2>/dev/null | cut -f1 || echo 0)
  echo "[RM] $rel (${local_kb} KB)"
  chmod -R u+w "$target" 2>/dev/null || true
  if rm -rf "$target" 2>/dev/null; then
    removed=1
  else
    find "$target" -type f -exec chmod u+w {} + 2>/dev/null || true
    find "$target" -depth -delete 2>/dev/null && removed=1 || failed=1
  fi
  if [[ "$removed" -eq 1 ]]; then
    echo "[OK] entfernt: $rel"
  else
    echo "[WARN] teilweise/fehlgeschlagen: $rel (NTFS-Rechte — ggf. unter Windows leeren)" >&2
  fi
}

# Old project copies (canonical code lives in ~/active_alpha_model on SATA/ext4)
for name in \
  active_alpha_model \
  active_alpha_model_v5r_clean \
  active_alpha_model_v5r_final \
  active_alpha_model_v5r_submission; do
  remove_path "$name"
done

# Windows ballast (safe on Linux-only Active Alpha workflow)
for name in '$RECYCLE.BIN' pagefile.sys DumpStack.log.tmp; do
  remove_path "$name"
done

remove_path "active_alpha_project_review.zip"

echo "[OK] Ballast bereinigt. Frei:"
df -h "$mount" | tail -1
