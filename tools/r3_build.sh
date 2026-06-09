#!/usr/bin/env bash
# R3 Bau-Werkstatt — ohne Cursor bauen (Ollama + sichere Ausführung).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"

usage() {
  cat <<'EOF'
R3 Bau-Kernel — Cursor-Bauwerkstatt nachgebaut

  r3-build                          Status + Hilfe
  r3-build status                   letzter Kernel-Lauf
  r3-build "Aufgabe in Deutsch"     Agent-Schleife (liest, schreibt, testet)
  r3-build apply                    Warteschlange (plan-Modus)
  r3-build /bau run 'pytest …'      Einzelbefehl (Allowlist)

EOF
}

cmd="${1:-}"
shift || true

case "$cmd" in
  ""|help|-h|--help)
    usage
    exec "$PY" "$ROOT/tools/ai_kernel.py" r3-build
    ;;
  status)
    exec "$PY" "$ROOT/tools/ai_kernel.py" r3-build --utterance status
    ;;
  apply)
    exec "$PY" "$ROOT/tools/ai_kernel.py" r3-build --utterance apply
    ;;
  *)
    task="$cmd"
    if (($#)); then
      task="$task $*"
    fi
    exec "$PY" "$ROOT/tools/ai_kernel.py" r3-build --utterance "$task"
    ;;
esac
