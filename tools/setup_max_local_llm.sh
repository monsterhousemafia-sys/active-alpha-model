#!/usr/bin/env bash
# Max-Tier — RTX 3090: Chat 14B + Bau Coder-32B + Fallbacks
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"

echo "[MAX] Alpha Model — lokale KI Max-Tier (RTX 3090)"

if ! command -v ollama >/dev/null 2>&1; then
  if [[ -x "${HOME}/.local/share/ollama/bin/ollama" ]]; then
    ln -sf "${HOME}/.local/share/ollama/bin/ollama" "${HOME}/.local/bin/ollama"
  elif command -v curl >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh
  else
    bash "$ROOT/tools/setup_local_llm_user.sh" || true
  fi
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "[FEHLER] ollama nicht im PATH"
  exit 1
fi

if ! ollama list >/dev/null 2>&1; then
  echo "[INFO] Starte ollama serve …"
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  sleep 4
fi

MODELS=(
  "qwen2.5:14b"
  "qwen2.5-coder:32b"
  "qwen2.5-coder:14b"
  "qwen2.5-coder:7b"
  "qwen2.5:7b"
)

for m in "${MODELS[@]}"; do
  if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$m"; then
    echo "[OK] Bereits installiert: $m"
    continue
  fi
  echo "[PULL] $m — kann bei 32B viele Minuten dauern …"
  ollama pull "$m"
done

echo "[VERIFY] Health …"
"$PY" tools/active_alpha_chat.py --health
"$PY" -c "
from pathlib import Path
from aa_safe_io import atomic_write_json
from datetime import datetime, timezone
from analytics.local_llm_bridge import health_report

root = Path('$ROOT')
h = health_report(root)
doc = {
    'schema_version': 1,
    'headline_de': 'Max-Tier RTX 3090 — Chat 14B, Bau Coder-32B',
    'ran_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    'gpu_tier_de': 'max_rtx3090',
    'health': h,
    'operator_next_de': 'alpha-model-agent',
}
atomic_write_json(root / 'evidence/local_llm_max_tier_latest.json', doc)
print('[OK] evidence/local_llm_max_tier_latest.json')
"

echo "[OK] Max-Tier bereit — alpha-model-agent"
