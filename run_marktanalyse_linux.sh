#!/usr/bin/env bash
# Linux GUI — PySide6 Invest-UI (aa_pilot_launch.py). Bash nur ohne Display oder mit --bash.
set -euo pipefail
cd "$(dirname "$0")"

export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$PWD"

for a in "$@"; do
  case "$a" in
    --bash|--headless) exec bash tools/marktanalyse_bash.sh start ;;
  esac
done

if [[ "${AA_MARKTANALYSE_BASH:-}" == "1" ]]; then
  exec bash tools/marktanalyse_bash.sh start "$@"
fi

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "[Hinweis] Kein Display — starte Bash-Cockpit." >&2
  exec bash tools/marktanalyse_bash.sh start "$@"
fi

PY=".venv/bin/python3"
[[ -x "$PY" ]] || PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[FEHLER] .venv fehlt — bash tools/setup_linux_native.sh" >&2
  exit 1
fi

args=()
for a in "$@"; do
  case "$a" in
    --dev|--skip-preflight) args+=(--skip-preflight) ;;
    --preflight-only) args+=(--preflight-only) ;;
  esac
done

exec "$PY" aa_pilot_launch.py "${args[@]}"
