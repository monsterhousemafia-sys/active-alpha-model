#!/usr/bin/env bash
# Kompatibilität — leitet an tools/marktanalyse_bash.sh weiter.
set -euo pipefail
cd "$(dirname "$0")"
export AA_PROJECT_ROOT="$PWD"
export AA_MARKTANALYSE_BASH=1
exec bash tools/marktanalyse_bash.sh "${1:-start}" "${@:2}"
