#!/usr/bin/env bash
# Remote Federation: Tunnel + Token + Lite-ZIP — Worker über Internet (WhatsApp etc.)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"

MODE="${AA_REMOTE_MODE:-auto}"

echo "=== Active Alpha — Remote Federation ==="
echo "[1/4] cloudflared …"
bash "$ROOT/tools/install_cloudflared.sh"

echo "[2/4] Remote-Hub (Tailscale oder Cloudflare) …"
"$PY" "$ROOT/tools/ai_kernel.py" spread-remote --mode "$MODE"
echo ""
echo "[fertig] ZIP unter ~/active_alpha_worker_LITE.zip — jetzt per WhatsApp/E-Mail verschicken."
