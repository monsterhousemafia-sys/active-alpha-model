#!/usr/bin/env bash
# Fail-closed safety — source from king_common (no orders, dry-run, review mode).
# shellcheck disable=SC2034
if [[ -z "${KING_SAFE_LOADED:-}" ]]; then
  KING_SAFE_LOADED=1
  _KING_SAFE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # shellcheck source=tools/linux_env.sh
  [[ -f "$_KING_SAFE_DIR/linux_env.sh" ]] && source "$_KING_SAFE_DIR/linux_env.sh"
  export AA_NO_LIVE_ORDER_SUBMISSION=1
  export AA_EXECUTION_DRY_RUN=1
  unset AA_LINUX_ALLOW_LIVE_ORDERS 2>/dev/null || true
fi
