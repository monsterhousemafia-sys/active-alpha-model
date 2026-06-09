#!/usr/bin/env bash
# Alpha Model — Entfaltungsraum (Auto lokal, voller Kontext)
set -euo pipefail
_SCRIPT="${BASH_SOURCE[0]}"
while [[ -L "$_SCRIPT" ]]; do
  _DIR="$(cd "$(dirname "$_SCRIPT")" && pwd)"
  _SCRIPT="$(readlink "$_SCRIPT")"
  [[ "$_SCRIPT" != /* ]] && _SCRIPT="$_DIR/$_SCRIPT"
done
ROOT="$(cd "$(dirname "$_SCRIPT")/.." && pwd)"
export AA_PROJECT_ROOT="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export AA_LINUX_NATIVE_APP=1
export AA_AGENT_CHAMBER=1
export AA_AGENT_SERVE=1
export AA_KING_CONTROL=1
export AA_OPERATOR_CHANNEL=conversational
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
"$PY" -c "
from pathlib import Path
from analytics.alpha_model_king_control import ensure_king_control, format_king_gate_de
r = Path('$ROOT')
king = ensure_king_control(r, repair=True)
if not king.get('ready'):
    print(format_king_gate_de(r))
    raise SystemExit(2)
"
# Bash-Tune beim Start (non-blocking Maintain+Status, H1-Watch wenn Benchmark läuft)
bash "$ROOT/tools/king_tune.sh" --no-watch >/dev/null 2>&1 &
# Coder-32B vorwärmen — nicht während build-kernel (GPU-Konkurrenz)
if ! pgrep -f "ai_kernel.py build-kernel" >/dev/null 2>&1; then
  (
    "$PY" -c "
from pathlib import Path
from analytics.alpha_model_entfaltung_32b import preload_build_model
preload_build_model(Path('$ROOT'))
" >/dev/null 2>&1
  ) &
fi
exec "$PY" "$ROOT/tools/active_alpha_chat.py" "$@"
