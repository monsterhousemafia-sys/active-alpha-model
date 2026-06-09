#!/usr/bin/env bash
# Portable Einstieg — USB-Stick oder beliebiger Pfad (setzt AA_PROJECT_ROOT).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1
cd "$ROOT"

PY="$ROOT/.venv/bin/python3"
REQ="$ROOT/requirements_active_alpha.txt"
LOCK="$ROOT/control/usb_pip_freeze.txt"

venv_ok() {
  [[ -x "$PY" ]] && "$PY" -c "import pandas, numpy, yaml" >/dev/null 2>&1
}

repair_venv() {
  echo "[usb] venv prüfen/reparieren unter $ROOT …"
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -U pip wheel
  if [[ -f "$LOCK" ]]; then
    "$ROOT/.venv/bin/pip" install -r "$LOCK"
  elif [[ -f "$REQ" ]]; then
    "$ROOT/.venv/bin/pip" install -r "$REQ"
  else
    echo "[FEHLER] Weder $LOCK noch $REQ gefunden." >&2
    exit 1
  fi
  PY="$ROOT/.venv/bin/python3"
}

patch_paths() {
  echo "[usb] Pfade in control/*.json an $ROOT anpassen …"
  SRC="${1:-}"
  if [[ -z "$SRC" && -f "$ROOT/control/usb_deploy_manifest.json" ]]; then
    SRC="$("$PY" -c "
import json
from pathlib import Path
d=json.loads(Path('$ROOT/control/usb_deploy_manifest.json').read_text(encoding='utf-8'))
print(d.get('source_project_root') or '')
" 2>/dev/null || true)"
  fi
  "$PY" "$ROOT/tools/usb_portable_finalize.py" "$ROOT" "${SRC:-$ROOT}" "runtime" >/dev/null
}

install_timers() {
  echo "[usb] systemd-Timer für $ROOT installieren …"
  bash "$ROOT/tools/setup_linux_daily_timers.sh"
}

verify_copy() {
  "$PY" "$ROOT/tools/usb_portable_finalize.py" --verify-only "$ROOT"
}

install_local() {
  local dest="${1:-$HOME/active_alpha_model}"
  echo "[usb] Spiegel nach $dest (ext4 — empfohlen für Dauerbetrieb) …"
  mkdir -p "$dest"
  rsync -a --delete --copy-links \
    --exclude '__pycache__/' --exclude '.pytest_cache/' \
    --exclude 'robustness_results_trading212\_shared_cache/' \
    --exclude '*.sock' \
    "$ROOT/" "$dest/"
  AA_PROJECT_ROOT="$dest" bash "$dest/USB_WEITERARBEITEN.sh" --repair-only
  AA_PROJECT_ROOT="$dest" ROOT="$dest" PY="$dest/.venv/bin/python3" \
    "$PY" "$dest/tools/usb_portable_finalize.py" "$dest" "$ROOT" "local_install"
  echo "[OK] Lokal installiert: $dest"
  echo "     cd $dest && ./USB_WEITERARBEITEN.sh --timers-only"
}

full_setup() {
  local dest="${1:-$HOME/active_alpha_model}"
  install_local "$dest"
  cd "$dest"
  export AA_PROJECT_ROOT="$dest"
  install_timers
  patch_paths "$ROOT"
  echo "[usb] king_ops Status …"
  bash "$dest/tools/king_ops.sh" status 2>/dev/null | head -12 || true
  verify_copy || echo "[WARN] Verifikation mit Hinweisen — siehe oben."
  echo ""
  echo "[OK] Vollständiger Setup-Pfad: $dest"
  echo "     Hub:  $dest/.venv/bin/python $dest/tools/preview_hub.py --ensure"
  echo "     R3:   http://127.0.0.1:17890/r3"
}

case "${1:-}" in
  --repair-only)
    venv_ok || repair_venv
    ;;
  --patch-paths)
    venv_ok || repair_venv
    patch_paths "${2:-}"
    ;;
  --timers-only)
    venv_ok || repair_venv
    install_timers
    ;;
  --verify)
    venv_ok || repair_venv
    verify_copy
    ;;
  --install-local)
    install_local "${2:-}"
    ;;
  --full-setup)
    full_setup "${2:-}"
    ;;
  --help|-h)
    cat <<EOF
Usage:
  ./USB_WEITERARBEITEN.sh                 # venv prüfen, Kurzinfo
  ./USB_WEITERARBEITEN.sh --full-setup    # empfohlen: ext4 + Timer + Pfade + Verify
  ./USB_WEITERARBEITEN.sh --install-local [~/active_alpha_model]
  ./USB_WEITERARBEITEN.sh --timers-only   # nur systemd-Timer neu
  ./USB_WEITERARBEITEN.sh --verify        # Kopie prüfen

Einmal nach USB-Stecken: --full-setup — danach wie bisher (king_ops, R3, 24/7-Timer).
T212-Keys: gleicher PC = Keyring bleibt; neuer PC = Zugangsdaten neu eintragen.
EOF
    ;;
  *)
    venv_ok || repair_venv
    patch_paths
    echo "[OK] AA_PROJECT_ROOT=$ROOT"
    echo "     Empfohlen: ./USB_WEITERARBEITEN.sh --full-setup"
    echo "     Hub:  $PY tools/preview_hub.py --ensure"
    echo "     Ops:  bash tools/king_ops.sh status"
    ;;
esac
