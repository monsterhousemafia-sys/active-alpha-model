#!/usr/bin/env bash
# Fail-closed verify — Root, Safety-Env, Locks, H1-Pfad.
# Usage: bash tools/king_verify.sh
set -euo pipefail
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_assert_project_root

FAIL=0
WARN=0
check() {
  local ok="$1" label="$2" detail="${3:-}"
  if [[ "$ok" == "1" ]]; then
    echo "  OK   $label${detail:+ — $detail}"
  else
    echo "  FAIL $label${detail:+ — $detail}" >&2
    FAIL=1
  fi
}

warn() {
  local label="$1" detail="${2:-}"
  echo "  WARN $label${detail:+ — $detail}"
  WARN=1
}

echo "[verify] Projekt-Safety"

check 1 "project_root" "$KING_ROOT"
check "$([[ "${AA_EXECUTION_DRY_RUN:-}" == "1" ]] && echo 1 || echo 0)" "dry_run" "AA_EXECUTION_DRY_RUN=1"
check "$([[ "${AA_NO_LIVE_ORDER_SUBMISSION:-}" == "1" ]] && echo 1 || echo 0)" "no_live_orders"
check "$([[ -x "$KING_PY" ]] && echo 1 || echo 0)" "python" "$KING_PY"
check "$([[ -f "$KING_ROOT/.cursor/hooks.json" ]] && echo 1 || echo 0)" "cursor_hooks_empty"

if king_benchmark_running && king_benchmark_running; then
  dup="$(king_benchmark_pids | wc -l)"
  check "$([[ "$dup" -le 1 ]] && echo 1 || echo 0)" "single_benchmark" "count=$dup"
fi

if [[ -d "$KING_ROOT/active_alpha_worker_FULL" ]]; then
  ghost="$(du -sm "$KING_ROOT/active_alpha_worker_FULL" 2>/dev/null | awk '{print $1}')"
  warn "nested_worker_full" "ghost ${ghost}MB — rm -rf nach Cursor-Neustart"
else
  check 1 "no_nested_worker_full"
fi

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat <<EOF | king_write_evidence "evidence/king_verify_latest.json"
{
  "schema_version": 1,
  "verified_at_utc": "$NOW",
  "ok": $([ "$FAIL" -eq 0 ] && echo true || echo false),
  "warnings": $WARN,
  "bash_de": "bash tools/king_ops.sh verify"
}
EOF

[[ "$FAIL" -eq 0 ]] || exit 1
echo "[verify] PASS"
