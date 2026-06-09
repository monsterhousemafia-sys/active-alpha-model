#!/usr/bin/env bash
# König verteilt alles — ein Bash-Einstieg (Tunnel, ZIP, H1, Spread, Worker).
# Nutzung: bash tools/king_distribute.sh
# Chat:    /könig-verteilen  /bash-verteilen
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"
MODE="${AA_REMOTE_MODE:-auto}"

echo "=============================================="
echo " KÖNIG — Alles verteilen (Bash-Orchestrator)"
echo "=============================================="

echo "[1/6] Hub online …"
"$PY" "$ROOT/tools/preview_hub.py" --ensure 2>/dev/null || true

echo "[2/6] Tunnel + Welt-Runtime …"
bash "$ROOT/tools/install_cloudflared.sh" 2>/dev/null || true
"$PY" "$ROOT/tools/ai_kernel.py" world-spread --mode "$MODE" || {
  echo "[WARN] world-spread — versuche spread-remote …" >&2
  "$PY" "$ROOT/tools/ai_kernel.py" spread-remote --mode "$MODE"
}

echo "[3/6] Spread intensivieren (Demand, Timer, Forum) …"
"$PY" "$ROOT/tools/ai_kernel.py" spread-intensify --mode "$MODE"

echo "[4/6] H1-Verteilung + Worker-Status …"
"$PY" "$ROOT/tools/ai_kernel.py" h1-distribute
"$PY" "$ROOT/tools/ai_kernel.py" h1-workers || true

echo "[5/6] Worker auf König-Host …"
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_init
if king_benchmark_running; then
  echo "    Benchmark läuft — kein Worker/pkill (H1-Seal geschützt)"
elif [[ "${AA_WEG_B:-${AA_KING_ORCHESTRATE_ONLY:-}}" =~ ^(1|true|yes)$ ]]; then
  pkill -f "preview_federation_worker.py --join" 2>/dev/null || true
  echo "    Weg B — nur Orchestrierung (Benchmark nicht aktiv)"
else
  if ! pgrep -f "preview_federation_worker.py --join" >/dev/null 2>&1; then
    nohup "$PY" "$ROOT/tools/preview_federation_worker.py" \
      --join http://127.0.0.1:17890 --no-preview --interval 30 \
      >> "$ROOT/evidence/federation_local_worker.log" 2>&1 &
    echo "    Worker-Daemon gestartet (30s)"
  else
    echo "    Worker-Daemon läuft bereits"
  fi
fi

echo "[6/6] Community-Text (zum Teilen) …"
bash "$ROOT/tools/preview_spread.sh"

echo ""
echo "=============================================="
echo " Fertig — Evidence: evidence/king_distribute_latest.json"
echo " ZIP: ~/active_alpha_worker_LITE.zip"
echo " Prüfen: python3 tools/ai_kernel.py h1-workers"
echo "=============================================="

"$PY" -c "
import json
from datetime import datetime, timezone
from pathlib import Path
root = Path('$ROOT')
out = {'schema_version': 1, 'ok': True, 'distributed_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
for rel in (
    'evidence/world_spread_latest.json',
    'evidence/spread_intensify_latest.json',
    'evidence/h1_distribute_latest.json',
    'evidence/federation_assignments_latest.json',
):
    p = root / rel
    if p.is_file():
        try:
            out[rel.replace('evidence/', '').replace('.json', '')] = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            pass
lite = root.parent / 'active_alpha_worker_LITE.zip'
out['lite_zip'] = str(lite) if lite.is_file() else None
out['headline_de'] = (out.get('world_spread_latest') or {}).get('headline_de') or 'König-Verteilung abgeschlossen'
out['bash_de'] = 'bash tools/king_distribute.sh'
path = root / 'evidence/king_distribute_latest.json'
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(out.get('headline_de'))
"
