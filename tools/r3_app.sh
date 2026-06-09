#!/usr/bin/env bash
# R3 — lokale Qt-App (delegiert an r3_cockpit.sh, kein Browser).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
exec "$(dirname "$_SELF")/r3_cockpit.sh"
