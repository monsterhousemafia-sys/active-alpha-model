#!/usr/bin/env bash
# Move heavy archive dirs to NVMe and symlink back — keeps code/venv on ext4.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

PY=".venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

status="$("$PY" -c "
from pathlib import Path
import json
from execution.linux_nvme_storage import storage_status
print(json.dumps(storage_status(Path('$ROOT'))))
")"

mount="$(echo "$status" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("mount") or "")')"
data_root="$(echo "$status" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("data_root") or "")')"

if [[ -z "$mount" || -z "$data_root" ]]; then
  echo "[FEHLER] NVMe nicht eingehängt — bitte Datenträger D: mounten." >&2
  exit 1
fi

mkdir -p "$data_root"

echo "[INFO] Repariere kaputte Symlinks …"
"$PY" -c "
from pathlib import Path
from execution.linux_nvme_storage import repair_migrated_symlinks
import json
print(json.dumps(repair_migrated_symlinks(Path('$ROOT')), indent=2))
"

h1_active_run() {
  "$PY" -c "
from pathlib import Path
from analytics.live_profile_governance import h1_backtest_status
st = h1_backtest_status(Path('$ROOT'))
if str(st.get('status') or '') != 'RUNNING':
    raise SystemExit(0)
rd = str(st.get('run_dir') or '')
print(Path(rd).name if rd else '')
" 2>/dev/null || true
}

migrate_one() {
  local name="$1"
  local src="$ROOT/$name"
  local dst="$data_root/$name"
  if [[ -L "$src" ]]; then
    echo "[OK] $name bereits Symlink → $(readlink -f "$src")"
    return 0
  fi
  if [[ ! -e "$src" ]]; then
    echo "[SKIP] $name fehlt"
    return 0
  fi
  if [[ -d "$dst" ]]; then
    if [[ -e "$src" && ! -L "$src" ]]; then
      local_kb=$(du -sk "$src" 2>/dev/null | cut -f1 || echo 0)
      if [[ "${local_kb:-0}" -gt 8 ]]; then
        echo "[MERGE] $name → bestehendes NVMe"
        rsync -a --no-group --no-owner "$src/" "$dst/"
      fi
      rm -rf "$src"
    fi
    ln -sfn "$dst" "$src"
    echo "[LINK] $name → $dst"
    return 0
  fi
  echo "[MOVE] $name → $dst"
  mv "$src" "$dst"
  ln -sfn "$dst" "$src"
}

migrate_validation_runs_partial() {
  local active="$1"
  local src="$ROOT/validation_runs"
  local dst="$data_root/validation_runs"
  mkdir -p "$dst"
  if [[ -L "$src" ]]; then
    echo "[OK] validation_runs bereits Symlink"
    return 0
  fi
  shopt -s nullglob
  for run in "$src"/*/; do
    [[ -d "$run" ]] || continue
    base="$(basename "$run")"
    if [[ -n "$active" && "$base" == "$active" ]]; then
      echo "[KEEP] Aktiver H1-Lauf auf SATA: $base"
      continue
    fi
    if [[ -e "$dst/$base" ]]; then
      echo "[SKIP] $base bereits auf NVMe"
      continue
    fi
    echo "[MOVE] validation_runs/$base → NVMe"
    mv "$run" "$dst/$base"
  done
  if [[ ! -e "$src/.nvme_partial" ]]; then
    echo "partial — aktiver H1-Lauf bleibt lokal bis COMPLETE" >"$src/.nvme_partial"
  fi
  echo "[OK] validation_runs teilweise auf NVMe (aktiv: ${active:-—})"
}

mapfile -t dirs < <("$PY" -c "
from pathlib import Path
from execution.linux_nvme_storage import migrate_dir_names
for n in migrate_dir_names(Path('$ROOT')):
    print(n)
")

ACTIVE_H1="$(h1_active_run)"
for d in "${dirs[@]}"; do
  if [[ "$d" == "validation_runs" && -n "$ACTIVE_H1" ]]; then
    migrate_validation_runs_partial "$ACTIVE_H1"
    continue
  fi
  if [[ -n "$ACTIVE_H1" && "$d" == "model_output_sp500_pit_t212" ]]; then
    echo "[SKIP] model_output — H1 RUNNING nutzt Cache (nach COMPLETE: setup_nvme_storage.sh erneut)"
    continue
  fi
  migrate_one "$d"
done

cache="$data_root/shared_cache"
mkdir -p "$cache"
echo "[OK] NVMe-Datentier: $data_root"
echo "[OK] Shared cache: $cache"
echo "[OK] Frei auf NVMe: $(echo "$status" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("free_gb"))') GB"
echo "       AA_SHARED_CACHE_DIR=$cache"
