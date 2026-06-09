#!/usr/bin/env bash
# Legacy — leitet an apps-run (ein build-kernel-Pfad).
set -euo pipefail
echo "[32B] desktop-finish → apps-run (konsolidiert)" >&2
exec bash "$(cd "$(dirname "$0")" && pwd)/king_ops.sh" apps-run
