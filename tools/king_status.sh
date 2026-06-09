#!/usr/bin/env bash
# König-Status — PID, CSV, Seal, Governance (schnell, ohne Ollama).
# Usage: bash tools/king_status.sh [--json]
set -euo pipefail
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_assert_project_root

JSON_ONLY=0
[[ "${1:-}" == "--json" ]] && JSON_ONLY=1

CSV="$(king_h1_csv_path)"
CSV_OK=0
CSV_BYTES=0
if [[ -n "$CSV" && -f "$CSV" ]]; then
  CSV_BYTES="$(stat -c%s "$CSV" 2>/dev/null || echo 0)"
  [[ "$CSV_BYTES" -gt 100 ]] && CSV_OK=1
fi

BENCH_RUNNING=0
BENCH_PID=""
if king_benchmark_running; then
  BENCH_RUNNING=1
  BENCH_PID="$(king_benchmark_pid)"
fi

SEALED=0
king_h1_sealed && SEALED=1

H1_STATUS="$(king_h1_status)"
H1_STATUS="${H1_STATUS:-UNKNOWN}"
GOV_CHAMP="$(king_json_field "$KING_ROOT/control/strategic_governance.json" "governance_champion")"
GOV_CHAMP="${GOV_CHAMP:-?}"

ORPHAN_MB=0
if [[ -d "$KING_ROOT/evidence" ]]; then
  ORPHAN_MB="$(find "$KING_ROOT/evidence" -maxdepth 1 -name '.*' -type f -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {printf "%d", (s+524287)/1048576}')"
fi

GHOST_MB=0
if [[ -d "$KING_ROOT/active_alpha_worker_FULL" ]]; then
  GHOST_MB="$(du -sm "$KING_ROOT/active_alpha_worker_FULL" 2>/dev/null | awk '{print $1}' || echo 0)"
fi

BENCH_HUNG=0
BENCH_ELAPSED=0
if [[ "$BENCH_RUNNING" -eq 1 ]]; then
  BENCH_ELAPSED="$(king_benchmark_elapsed_s 2>/dev/null || echo 0)"
  king_log_hung_once || true
  king_benchmark_hung && BENCH_HUNG=1
fi

SAFE_DRY="${AA_EXECUTION_DRY_RUN:-0}"

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

SEAL_REQUIRED=1
if ! "$KING_PY" -c "from pathlib import Path; from analytics.h1_seal_policy import is_h1_seal_required; raise SystemExit(0 if is_h1_seal_required(Path('$KING_ROOT')) else 1)" 2>/dev/null; then
  SEAL_REQUIRED=0
fi

NEXT_ACTION="$(
  if [[ "$SEALED" -eq 1 ]]; then echo '/ready — H1 sealed'
  elif [[ "$SEAL_REQUIRED" -eq 0 && "$H1_STATUS" == "COMPLETE" ]]; then echo '/ready — H1 COMPLETE; Seal optional · /predict'
  elif [[ "$BENCH_HUNG" -eq 1 ]]; then echo 'bash tools/king_ops.sh status — Benchmark prüfen (hung?)'
  elif [[ "$SEAL_REQUIRED" -eq 1 && "$CSV_OK" -eq 1 ]]; then echo 'bash tools/king_ops.sh h1-seal'
  elif [[ "$SEAL_REQUIRED" -eq 1 && "$BENCH_RUNNING" -eq 1 ]]; then echo 'bash tools/king_ops.sh watch-bg'
  elif [[ "$SEAL_REQUIRED" -eq 1 ]]; then echo 'bash tools/king_ops.sh h1-seal'
  else echo '/predict — Seal optional'
  fi
)"
NEXT_LAYER="$(
  if [[ "$SEALED" -eq 1 ]]; then echo 'koenig'
  elif [[ "$SEAL_REQUIRED" -eq 0 && "$H1_STATUS" == "COMPLETE" ]]; then echo 'koenig'
  elif [[ "$BENCH_HUNG" -eq 1 ]]; then echo 'koenig'
  elif [[ "$SEAL_REQUIRED" -eq 1 && "$CSV_OK" -eq 1 ]]; then echo 'bash'
  elif [[ "$SEAL_REQUIRED" -eq 1 && "$BENCH_RUNNING" -eq 1 ]]; then echo 'bash'
  elif [[ "$SEAL_REQUIRED" -eq 1 ]]; then echo 'bash'
  else echo 'koenig'
  fi
)"

DOC="$(
  cat <<EOF
{
  "schema_version": 2,
  "matrix_ref": "control/king_responsibility_matrix_de.md",
  "layer": "bash",
  "checked_at_utc": "$NOW",
  "h1_status": "$H1_STATUS",
  "h1_sealed": $([ "$SEALED" -eq 1 ] && echo true || echo false),
  "benchmark_running": $([ "$BENCH_RUNNING" -eq 1 ] && echo true || echo false),
  "benchmark_pid": ${BENCH_PID:-null},
  "benchmark_csv": $( [[ -n "$CSV" ]] && printf '"%s"' "$CSV" || echo null ),
  "benchmark_csv_ok": $([ "$CSV_OK" -eq 1 ] && echo true || echo false),
  "benchmark_csv_bytes": $CSV_BYTES,
  "governance_champion": "$GOV_CHAMP",
  "orphan_evidence_mb": $ORPHAN_MB,
  "ghost_worker_full_mb": $GHOST_MB,
  "benchmark_elapsed_s": $BENCH_ELAPSED,
  "benchmark_hung": $([ "$BENCH_HUNG" -eq 1 ] && echo true || echo false),
  "safety_dry_run": $([ "$SAFE_DRY" == "1" ] && echo true || echo false),
  "next_action_de": "$NEXT_ACTION",
  "next_layer": "$NEXT_LAYER",
  "bash_de": "bash tools/king_ops.sh status"
}
EOF
)"

echo "$DOC" | king_write_evidence "evidence/king_status_latest.json"
"$KING_PY" -c "
from pathlib import Path
import json
from aa_safe_io import atomic_write_json
from analytics.king_hardware import enrich_king_status_doc
from analytics.h1_benchmark_lessons import record_benchmark_lessons
root = Path('$KING_ROOT')
p = root / 'evidence/king_status_latest.json'
base = json.loads(p.read_text(encoding='utf-8'))
enriched = enrich_king_status_doc(base, root)
atomic_write_json(p, enriched)
if enriched.get('benchmark_over_eta') or enriched.get('benchmark_running'):
    record_benchmark_lessons(root, trigger_de='king_status')
" 2>/dev/null || true
PULSE="$(king_sync_network bash 2>/dev/null || echo "")"
HW_LINE="$("$KING_PY" -c "
import json
from pathlib import Path
p = Path('$KING_ROOT/evidence/king_hardware_latest.json')
if not p.is_file():
    print('')
else:
    d = json.loads(p.read_text(encoding='utf-8'))
    g = 'ON' if (d.get('gpu_returns') or {}).get('enabled') else 'OFF'
    print(f\"GPU-Returns {g} · NVMe {'ja' if d.get('nvme_mounted') else 'nein'} · {d.get('vram_policy_de','')[:70]}\")
" 2>/dev/null || echo "")"

if [[ "$JSON_ONLY" -eq 1 ]]; then
  echo "$DOC"
  exit 0
fi

echo "=============================================="
echo " KÖNIG STATUS — $(date -u +%H:%M:%S) UTC"
echo "=============================================="
echo " H1 Backtest:     $H1_STATUS"
echo " H1 Sealed:       $([ "$SEALED" -eq 1 ] && echo JA || echo NEIN)"
echo " Benchmark PID:   ${BENCH_PID:-—} $([ "$BENCH_RUNNING" -eq 1 ] && echo "(läuft ${BENCH_ELAPSED}s)" || echo '')"
echo " Benchmark hung:  $([ "$BENCH_HUNG" -eq 1 ] && echo JA || echo nein)"
OVER_ETA="$("$KING_PY" -c "import json; print('ja' if json.load(open('$KING_ROOT/evidence/king_status_latest.json')).get('benchmark_over_eta') else 'nein')" 2>/dev/null || echo nein)"
echo " Über ETA:       $OVER_ETA"
echo " Seal-CSV:        ${CSV:-fehlt} ($CSV_BYTES bytes) $([ "$CSV_OK" -eq 1 ] && echo OK || echo FEHLT)"
echo " Safety:          dry_run=$SAFE_DRY no_orders=${AA_NO_LIVE_ORDER_SUBMISSION:-?}"
echo " Champion:        $GOV_CHAMP"
echo " Evidence-Müll:   ${ORPHAN_MB} MB (.aa_* orphans)"
echo " worker_FULL:     ${GHOST_MB} MB"
DISPLAY_NEXT="$("$KING_PY" -c "import json; d=json.load(open('$KING_ROOT/evidence/king_status_latest.json')); print(d.get('next_action_de',''))" 2>/dev/null || echo "$NEXT_ACTION")"
DISPLAY_LAYER="$("$KING_PY" -c "import json; d=json.load(open('$KING_ROOT/evidence/king_status_latest.json')); print(d.get('next_layer',''))" 2>/dev/null || echo "$NEXT_LAYER")"
echo "----------------------------------------------"
echo " Nächster Schritt (${DISPLAY_LAYER:-$NEXT_LAYER}):"
echo " ${DISPLAY_NEXT:-$NEXT_ACTION}"
if [[ -n "$HW_LINE" ]]; then
  echo "----------------------------------------------"
  echo " Hardware:"
  echo " $HW_LINE"
fi
if [[ -n "$PULSE" ]]; then
  echo "----------------------------------------------"
  echo " Netzwerk-Takt:"
  echo " $PULSE"
fi
echo "=============================================="
