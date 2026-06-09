#!/usr/bin/env bash
# Ubuntu → R3 + ULWO Launch — Abschluss.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
export R3_SESSION=1

echo "=== Ubuntu → R3 — Abschluss + ULWO Launch ==="

"$PY" "$ROOT/tools/ai_kernel.py" ulwo-launch

echo ""
echo "[OK] Download: http://127.0.0.1:17890/download"
echo "[OK] ZIP:      http://127.0.0.1:17890/api/ulwo/bundle.zip"
echo "[OK] Install:  curl -fsSL http://127.0.0.1:17890/api/ulwo/install.sh | ULWO_HUB=http://127.0.0.1:17890 bash"
echo ""
echo "Neustart in 5 Sekunden (Strg+C zum Abbrechen) ..."
sleep 5
sudo reboot
