#!/usr/bin/env bash
# OpenAI-Key für König-Berater-Bridge — interaktiv, nur Keyring, nie Chat
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AA_PROJECT_ROOT="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
echo "Berater-Bridge — OpenAI Key einrichten (Eingabe unsichtbar)"
"$PY" tools/ai_kernel.py advisor-key-setup
