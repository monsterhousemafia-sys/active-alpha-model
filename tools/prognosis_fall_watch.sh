#!/usr/bin/env bash
# Ganztägiger Fall-Wächter — ein Tick oder Dauerschleife bis Fall erkannt.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

MODE="${1:-once}"
INTERVAL="${PROGNOSIS_FALL_WATCH_INTERVAL_S:-900}"

run_tick() {
  "$PY" -c "
from pathlib import Path
from analytics.prognosis_fall_watch import run_fall_watch
import json, sys
doc = run_fall_watch(Path('$ROOT'), persist=True, fetch_live=True)
print(doc.get('headline_de',''))
if doc.get('justification',{}).get('reasons_de'):
    for r in doc['justification']['reasons_de']:
        print(' ·', r)
print(json.dumps({
    'fall_detected': doc.get('fall_detected'),
    'portfolio_return_pct': doc.get('portfolio_return_pct'),
    'benchmark_return_pct': doc.get('benchmark_return_pct'),
}, ensure_ascii=False))
sys.exit(0 if doc.get('fall_detected') else 2)
"
}

case "$MODE" in
  once|tick)
    run_tick || true
    ;;
  loop|watch)
    echo "Fall-Wächter: Intervall ${INTERVAL}s — stop bei Fall erkannt"
    while true; do
      if run_tick; then
        echo "AGENT_FALL_DETECTED $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        exit 0
      fi
      sleep "$INTERVAL"
    done
    ;;
  status)
    "$PY" -c "
from pathlib import Path
import json
p = Path('$ROOT') / 'evidence/prognosis_fall_watch_latest.json'
print(p.read_text(encoding='utf-8') if p.is_file() else '{}')
"
    ;;
  *)
    echo "Usage: $0 once|loop|status"
    exit 1
    ;;
esac
