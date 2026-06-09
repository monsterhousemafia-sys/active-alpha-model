#!/usr/bin/env bash
# König-Server: ein Hub, Tunnel, Autostart — ein Befehl.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"

if [[ -f "$ROOT/control/server.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/control/server.env"
  set +a
fi

if [[ -n "${AA_CLOUDFLARE_TUNNEL_TOKEN:-}" && ! -f "$ROOT/control/cloudflare_tunnel.token" ]]; then
  printf '%s' "$AA_CLOUDFLARE_TUNNEL_TOKEN" > "$ROOT/control/cloudflare_tunnel.token"
  chmod 600 "$ROOT/control/cloudflare_tunnel.token"
fi

exec "$PY" "$ROOT/tools/ai_kernel.py" server-bootstrap
