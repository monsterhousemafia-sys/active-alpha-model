#!/usr/bin/env bash
# Active-Alpha Linux Runtime — Slices, Limits, API, Evidence-Watch, Spread-Tick
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/.venv/bin/python3"
exec "${PY}" "${ROOT}/tools/ai_kernel.py" runtime-install
