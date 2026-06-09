#!/usr/bin/env bash
# Ein Spread-Einstieg — maximal effizient, fail-closed abgesichert.
# Usage: bash tools/spread_ops.sh [verify|haus|welt|voll|internet]
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/king_safe.sh
source "$(dirname "$_SELF")/king_safe.sh"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

MODE="${1:-voll}"
shift || true

export AA_PROJECT_ROOT="$R3_ROOT"
export AA_NO_LIVE_ORDER_SUBMISSION=1
export AA_EXECUTION_DRY_RUN=1

exec "$R3_PY" -c "
from pathlib import Path
from analytics.spread_secure_ops import run_spread_efficient, verify_spread_security
import json, sys

r = Path('$R3_ROOT')
mode = '${MODE}'
if mode == 'verify':
    doc = verify_spread_security(r)
else:
    doc = run_spread_efficient(r, mode)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
