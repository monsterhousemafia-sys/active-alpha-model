#!/usr/bin/env bash
# Headless Linux compute — predict, signal refresh, status. Never submits T212 orders.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/tools/linux_env.sh"
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

cmd="${1:-help}"
shift || true

case "$cmd" in
  predict)
    exec "$PY" -u tools/run_tomorrow_prediction.py "$@"
    ;;
  eod)
    exec "$PY" -u -c "from analytics.prediction_operations import run_eod_prediction_switch; import json,sys; from pathlib import Path; r=Path('.').resolve(); print(json.dumps(run_eod_prediction_switch(r, force='--force' in sys.argv), indent=2, default=str))"
    ;;
  status)
    exec "$PY" -u -c "from execution.linux_security_boundary import host_role_summary; import json; print(json.dumps(host_role_summary(), indent=2))"
    ;;
  verify)
    exec "$PY" -u tools/preflight_wsl_migration.py
    ;;
  help|*)
    cat <<'EOF'
linux_live_ops.sh — compute-only (fail-closed env loaded)

  predict [--profile daily_alpha_h1]   EOD / tomorrow signal
  eod [--force]                        EOD switch wrapper
  status                               Linux host role + guards
  verify                               WSL preflight

Orders: use Windows Marktanalyse.exe — never from this script.
EOF
    ;;
esac
