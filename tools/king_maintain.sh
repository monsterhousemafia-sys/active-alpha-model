#!/usr/bin/env bash
# Legacy alias — tune nutzt king_clean + verify. Nur clean + governance.
# Usage: bash tools/king_maintain.sh [--dry-run]
set -euo pipefail
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_assert_project_root

bash "$KING_ROOT/tools/king_clean.sh" "${1:-}"
"$KING_PY" "$KING_ROOT/tools/sync_strategic_governance.py" 2>/dev/null || true
"$KING_PY" "$KING_ROOT/tools/reconcile_governance_drift.py" >/dev/null 2>&1 || true
echo "[OK] maintain — siehe king_clean_latest.json"
