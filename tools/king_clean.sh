#!/usr/bin/env bash
# Safe cleanup — Müll, stale Locks, tote Watch-PIDs (kein rm -rf auf Daten).
# Usage: bash tools/king_clean.sh [--dry-run]
set -euo pipefail
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_assert_project_root

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

echo "[clean] Safe cleanup (dry_run=$DRY)"

removed=0
freed=0
while IFS= read -r -d '' f; do
  sz="$(stat -c%s "$f" 2>/dev/null || echo 0)"
  if [[ "$DRY" -eq 1 ]]; then
    echo "  dry-run rm: $f ($sz B)"
  else
    rm -f "$f" && echo "  rm: $f ($sz B)"
  fi
  removed=$((removed + 1))
  freed=$((freed + sz))
done < <(find "$KING_ROOT/evidence" -maxdepth 1 -name '.*' -type f -print0 2>/dev/null)

rm -f "$KING_LOCK_DIR/benchmark_hung_logged.flag" 2>/dev/null || true

if [[ -f "$KING_LOCK_DIR/h1_watch_bg.pid" ]]; then
  wp="$(cat "$KING_LOCK_DIR/h1_watch_bg.pid" 2>/dev/null || true)"
  if [[ -z "$wp" ]] || ! kill -0 "$wp" 2>/dev/null; then
    [[ "$DRY" -eq 1 ]] && echo "  dry-run stale watch pid" || rm -f "$KING_LOCK_DIR/h1_watch_bg.pid"
  fi
fi

AA_KING_MAINTAIN_DRY="$DRY" "$KING_PY" -c "
import os
from pathlib import Path
from aa_job_lock import pid_alive, read_lock_owner
root = Path('$KING_ROOT')
dry = os.environ.get('AA_KING_MAINTAIN_DRY', '0') == '1'
for p in (root / '.active_alpha_jobs').glob('*.lock'):
    if p.name.endswith('.pid'):
        continue
    pid = read_lock_owner(p)
    if pid is None or not pid_alive(pid):
        print(f'  stale lock: {p.name}' + (' (dry)' if dry else ''))
        if not dry:
            p.unlink(missing_ok=True)
"

ghost=0
[[ -d "$KING_ROOT/active_alpha_worker_FULL" ]] && ghost="$(du -sm "$KING_ROOT/active_alpha_worker_FULL" 2>/dev/null | awk '{print $1}' || echo 0)"

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat <<EOF | king_write_evidence "evidence/king_clean_latest.json"
{
  "schema_version": 1,
  "cleaned_at_utc": "$NOW",
  "ok": true,
  "orphan_files_removed": $removed,
  "orphan_bytes_freed": $freed,
  "ghost_worker_full_mb": $ghost,
  "ghost_note_de": "Manuell: rm -rf active_alpha_worker_FULL nach Cursor-Neustart",
  "dry_run": $([ "$DRY" -eq 1 ] && echo true || echo false),
  "bash_de": "bash tools/king_ops.sh clean"
}
EOF

echo "[clean] OK — $removed orphans (~$((freed / 1024)) KB), ghost=${ghost}MB"
