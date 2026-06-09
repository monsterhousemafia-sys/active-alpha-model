#!/usr/bin/env bash
# Shared helpers for König Bash orchestration (source only).
# shellcheck disable=SC2034
set -euo pipefail

# shellcheck source=tools/king_safe.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/king_safe.sh"

king_assert_project_root() {
  king_init
  if [[ ! -f "$KING_ROOT/aa_safe_io.py" || ! -d "$KING_ROOT/control" ]]; then
    echo "[king] FEHLER — kein gültiges Projekt-Root: $KING_ROOT" >&2
    exit 2
  fi
}

king_init() {
  if [[ -z "${KING_ROOT:-}" ]]; then
    local _src _dir
    _src="${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}"
    while [[ -L "$_src" ]]; do
      _dir="$(cd "$(dirname "$_src")" && pwd)"
      _src="$(readlink "$_src")"
      [[ "$_src" != /* ]] && _src="$_dir/$_src"
    done
    KING_ROOT="$(cd "$(dirname "$_src")/.." && pwd)"
  fi
  cd "$KING_ROOT"
  export AA_PROJECT_ROOT="$KING_ROOT"
  export AA_LINUX_NATIVE_APP=1
  KING_PY="$KING_ROOT/.venv/bin/python3"
  [[ -x "$KING_PY" ]] || KING_PY="$(command -v python3)"
  KING_LOCK_DIR="$KING_ROOT/.active_alpha_jobs"
  mkdir -p "$KING_LOCK_DIR" "$KING_ROOT/evidence"
}

king_run() {
  king_init
  "$KING_PY" "$KING_ROOT/tools/ai_kernel.py" "$@"
}

king_json_field() {
  local file="$1" expr="$2"
  king_init
  "$KING_PY" -c "
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
expr = sys.argv[2]
if not p.is_file():
    sys.exit(1)
doc = json.loads(p.read_text(encoding='utf-8'))
cur = doc
for part in expr.split('.'):
    if not part:
        continue
    if isinstance(cur, dict):
        cur = cur.get(part)
    else:
        cur = None
        break
if cur is None:
    sys.exit(1)
print(cur)
" "$file" "$expr" 2>/dev/null || true
}

king_h1_csv_path() {
  king_init
  "$KING_PY" -c "
from pathlib import Path
from analytics.h1_benchmark import _latest_run, expected_benchmark_path
root = Path('$KING_ROOT')
run = _latest_run(root)
if run is None:
    raise SystemExit(1)
print(expected_benchmark_path(run))
" 2>/dev/null || echo ""
}

king_benchmark_pids() {
  pgrep -af "[.]venv/bin/python.*tools/generate_h1_naive_benchmark.py" 2>/dev/null \
    | grep -v cursorsandbox \
    | grep -v 'pgrep -af' \
    | grep -v 'king_h1_seal' || true
}

king_benchmark_pid() {
  king_benchmark_pids | awk 'NR==1 {print $1}'
}

king_benchmark_running() {
  local pid
  pid="$(king_benchmark_pid)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

king_benchmark_elapsed_s() {
  local pid et
  pid="$(king_benchmark_pid)"
  [[ -n "$pid" ]] || return 1
  et="$(ps -p "$pid" -o etimes= 2>/dev/null | tr -d ' ' || true)"
  [[ -n "$et" ]] && echo "$et" || return 1
}

king_benchmark_hung() {
  local elapsed max_hung progress_age
  king_benchmark_running || return 1
  king_csv_ready && return 1
  elapsed="$(king_benchmark_elapsed_s || echo 0)"
  max_hung="${KING_BENCHMARK_HUNG_S:-5400}"
  [[ "$elapsed" -gt "$max_hung" ]] || return 1
  if [[ -f "$KING_ROOT/evidence/h1_benchmark_progress.json" ]]; then
    progress_age="$(( $(date +%s) - $(stat -c %Y "$KING_ROOT/evidence/h1_benchmark_progress.json" 2>/dev/null || echo 0) ))"
    [[ "$progress_age" -lt 900 ]] && return 1
  fi
  return 0
}

king_log_hung_once() {
  king_init
  local flag="$KING_LOCK_DIR/benchmark_hung_logged.flag"
  king_benchmark_hung || return 1
  [[ -f "$flag" ]] && return 0
  : >"$flag"
  echo "[king] WARNUNG — Benchmark hängt? elapsed=$(king_benchmark_elapsed_s)s, CSV fehlt" >&2
  cat <<EOF | king_write_evidence "evidence/king_benchmark_hung_latest.json"
{
  "schema_version": 1,
  "hung": true,
  "benchmark_pid": $(king_benchmark_pid || echo null),
  "elapsed_s": $(king_benchmark_elapsed_s || echo 0),
  "action_de": "Prüfen: bash tools/king_ops.sh status — Neustart nur manuell nach Prüfung",
  "updated_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
}

king_h1_sealed() {
  king_init
  local v py_sealed
  v="$(king_json_field "$KING_ROOT/control/h1_governance_status.json" "sealed")"
  if [[ "$v" == "True" || "$v" == "true" ]]; then
    return 0
  fi
  py_sealed="$("$KING_PY" -c "
from pathlib import Path
from analytics.live_profile_governance import is_h1_backtest_sealed
print('yes' if is_h1_backtest_sealed(Path('$KING_ROOT')) else 'no')
" 2>/dev/null || echo no)"
  [[ "$py_sealed" == "yes" ]]
}

king_h1_status() {
  king_init
  king_json_field "$KING_ROOT/control/h1_governance_status.json" "status"
}

king_csv_ready() {
  local csv size
  csv="$(king_h1_csv_path)"
  [[ -n "$csv" && -f "$csv" ]] || return 1
  size="$(stat -c%s "$csv" 2>/dev/null || echo 0)"
  [[ "$size" -gt 100 ]]
}

king_wait_benchmark() {
  local csv max_poll poll interval
  csv="$(king_h1_csv_path)"
  max_poll="${KING_BENCHMARK_MAX_WAIT_S:-5400}"
  interval="${KING_BENCHMARK_POLL_S:-30}"
  poll=0
  echo "[king] Warte auf Benchmark CSV: ${csv:-?} (max ${max_poll}s)"
  while (( poll < max_poll )); do
    if king_csv_ready; then
      echo "[king] CSV bereit"
      return 0
    fi
    if ! king_benchmark_running; then
      echo "[king] Benchmark-Prozess beendet ohne CSV" >&2
      return 1
    fi
    king_log_hung_once || true
    ps -p "$(king_benchmark_pid)" -o etime,pcpu --no-headers 2>/dev/null || true
    sleep "$interval"
    poll=$((poll + interval))
  done
  echo "[king] Timeout nach ${max_poll}s" >&2
  return 1
}

king_watch_bg_running() {
  king_init
  local pid
  [[ -f "$KING_LOCK_DIR/h1_watch_bg.pid" ]] || return 1
  pid="$(cat "$KING_LOCK_DIR/h1_watch_bg.pid" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

king_with_lock() {
  local lock_name="$1"
  shift
  king_init
  local lockfile="$KING_LOCK_DIR/${lock_name}.lock"
  (
    flock -n 9 || { echo "[king] Lock belegt: $lock_name" >&2; exit 3; }
    "$@"
  ) 9>"$lockfile"
}

king_write_evidence() {
  local rel="$1"
  king_init
  "$KING_PY" -c "
import json, sys
from pathlib import Path
from aa_safe_io import atomic_write_json
root = Path('$KING_ROOT')
doc = json.loads(sys.stdin.read())
atomic_write_json(root / sys.argv[1], doc)
" "$rel"
}

king_sync_network() {
  local source="${1:-bash}"
  king_init
  "$KING_PY" -c "
from pathlib import Path
from analytics.king_network import sync_network_pulse
doc = sync_network_pulse(Path('$KING_ROOT'), source_node='$source')
print(doc.get('headline_de') or 'network sync OK')
" 2>/dev/null || true
}
