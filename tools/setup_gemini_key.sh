#!/usr/bin/env bash
# Gemini API-Key einrichten — Google AI Studio Key für Cloud-Compute (/kombi, /tipp).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"

echo "[Gemini] API-Key für Cloud-Compute (Teacher-Student)"
echo "Key holen: https://aistudio.google.com/apikey"
echo ""
read -rsp "Gemini API Key (unsichtbar): " KEY
echo ""
if [[ -z "${KEY// }" ]]; then
  echo "[FEHLER] Kein Key eingegeben"
  exit 1
fi
printf '%s' "$KEY" | "$PY" tools/ai_kernel.py gemini-key-store
"$PY" tools/ai_kernel.py gemini-key-test
echo "[OK] Gemini aktiv — /kombi und /tipp nutzen jetzt Google Cloud-Compute"
