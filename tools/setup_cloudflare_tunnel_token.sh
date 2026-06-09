#!/usr/bin/env bash
set -euo pipefail
_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AA_PROJECT_ROOT="$_ROOT"
exec bash "$_ROOT/tools/king_ops.sh" tunnel-stable setup "$@"
