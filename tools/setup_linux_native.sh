#!/usr/bin/env bash
# Linux setup — same role as setup_active_alpha_env.bat
set -euo pipefail
cd "$(dirname "$0")/.."

pyver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

if ! python3 -m venv .venv 2>/dev/null; then
  python3 -m venv --without-pip .venv 2>/dev/null || true
fi

PY=".venv/bin/python3"
[[ -x "$PY" ]] || PY=".venv/bin/python"

bootstrap_pip() {
  if "$PY" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  echo "[INFO] pip fehlt — bootstrap via get-pip.py …" >&2
  tmp="$(mktemp)"
  if command -v wget >/dev/null 2>&1; then
    wget -q -O "$tmp" https://bootstrap.pypa.io/get-pip.py
  elif command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$tmp" https://bootstrap.pypa.io/get-pip.py
  else
    "$PY" -c "
import urllib.request
urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '$tmp')
"
  fi
  "$PY" "$tmp"
  rm -f "$tmp"
}

if ! bootstrap_pip; then
  echo "[FEHLER] pip konnte nicht installiert werden. Einmalig:" >&2
  echo "  sudo apt install python${pyver}-venv python3-pip" >&2
  exit 1
fi

"$PY" -m pip install -q --upgrade pip wheel
"$PY" -m pip install -q -r requirements_active_alpha.txt keyring SecretStorage pytest
echo "[OK] Setup fertig — bash run_marktanalyse_linux.sh --dev"
