#!/usr/bin/env bash
# Marktanalyse Bash — shared helpers (source only).
# shellcheck disable=SC2034
set -euo pipefail

# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/king_common.sh"

MA_EVIDENCE="evidence/marktanalyse_bash_latest.json"

ma_init() {
  king_init
  king_assert_project_root
  export AA_MARKTANALYSE_BASH=1
  export AA_NO_LIVE_ORDER_SUBMISSION=1
  export AA_EXECUTION_DRY_RUN=1
}

ma_banner() {
  local title="${1:-Marktanalyse}"
  echo "=============================================="
  echo " $title — Bash Cockpit"
  echo " $(ma_product_line)"
  echo " Safety: dry_run=1 · keine Linux-Orders"
  echo "=============================================="
}

ma_product_line() {
  ma_init
  "$KING_PY" -c "
from analytics.active_alpha_identity import status_line_de
from pathlib import Path
print(status_line_de(Path('$KING_ROOT')))
" 2>/dev/null || echo "Alpha Model · Bash"
}

ma_view() {
  local cmd="$1"
  shift || true
  ma_init
  "$KING_PY" "$KING_ROOT/tools/marktanalyse_bash_view.py" "$cmd" --root "$KING_ROOT" "$@"
}

ma_write_evidence() {
  ma_init
  ma_view bundle --json | king_write_evidence "$MA_EVIDENCE"
}

ma_section() {
  echo "----------------------------------------------"
  echo " $1"
  echo "----------------------------------------------"
}
