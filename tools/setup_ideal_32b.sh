#!/usr/bin/env bash
# Ideal-32B — König Chat+Bau (qwen2.5-coder:32b), Bash-Orchestrator
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"

echo "[Ideal-32B] König Coder-32B — Bash+Slash"

if ! command -v ollama >/dev/null 2>&1; then
  echo "[FEHLER] ollama nicht im PATH"
  exit 1
fi

if ! ollama list >/dev/null 2>&1; then
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  sleep 4
fi

"$PY" -c "
from pathlib import Path
from analytics.alpha_model_entfaltung_32b import apply_tier_to_llm_config
apply_tier_to_llm_config(Path('$ROOT'))
print('[OK] local_llm.json ← ideal_32b bash-lean')
"

MODELS=(
  "qwen2.5-coder:32b"
  "qwen2.5-coder:7b"
  "qwen2.5:7b"
)

for m in "${MODELS[@]}"; do
  if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$m"; then
    echo "[OK] $m"
    continue
  fi
  echo "[PULL] $m"
  ollama pull "$m"
done

echo "[PRELOAD] Coder-32B …"
"$PY" -c "
from pathlib import Path
from analytics.alpha_model_entfaltung_32b import preload_build_model, tier_status
r = Path('$ROOT')
pre = preload_build_model(r)
st = tier_status(r)
print('preload:', pre.get('ok'), pre.get('model'))
print('tier_ready:', st.get('tier_ready'), 'chat:', st.get('resolved_chat_model'))
"

echo "[OK] König bereit — alpha-model-agent"
