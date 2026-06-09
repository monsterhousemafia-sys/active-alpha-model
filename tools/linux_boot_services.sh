#!/usr/bin/env bash
# Post-boot / post-login downstream services (no sudo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
export AA_LINUX_NATIVE_APP=1

if [[ -f "$ROOT/control/preview_worker_join.json" ]]; then
  echo "[boot] preview worker bundle — federation bootstrap"
  bash "$ROOT/tools/bootstrap_preview_federation.sh" || true
  echo "[OK] worker boot complete"
  exit 0
fi

echo "[boot] nvme mount …"
udisksctl mount -b /dev/nvme0n1p1 2>/dev/null || true

echo "[boot] symlinks + price feed …"
"$PY" -c "
from pathlib import Path
from execution.linux_nvme_storage import repair_migrated_symlinks, apply_nvme_storage_env
from aa_adaptive_runtime import refresh_price_feed_state
import json
r = Path('$ROOT')
print(json.dumps(repair_migrated_symlinks(r), indent=2))
apply_nvme_storage_env(r)
print(json.dumps(refresh_price_feed_state(r), indent=2))
"

echo "[boot] headless snapshot …"
"$PY" "$ROOT/tools/ai_kernel.py" refresh --refresh-mode boot >/dev/null || true

echo "[boot] public status …"
"$PY" "$ROOT/tools/ai_kernel.py" visibility >/dev/null

echo "[boot] h1 governance …"
"$PY" -c "from pathlib import Path; from analytics.h1_governance_status import sync_h1_governance_status; sync_h1_governance_status(Path('$ROOT'))" 2>/dev/null || true

echo "[boot] reboot-apply (falls pending) …"
"$PY" -c "
from pathlib import Path
from analytics.reboot_full_apply import complete_after_reboot, reboot_pending
r = Path('$ROOT')
if reboot_pending(r):
    doc = complete_after_reboot(r)
    print(doc.get('headline_de') or 'reboot apply OK')
" 2>/dev/null || true

echo "[boot] preview hub (harmonized — kein server-bootstrap) …"
"$PY" -c "
from pathlib import Path
from analytics.linux_runtime_unified import ensure_preview_hub_boot
r = Path('$ROOT')
print(ensure_preview_hub_boot(r))
" 2>/dev/null || true

echo "[boot] h1-watch …"
"$PY" "$ROOT/tools/ai_kernel.py" h1-watch >/dev/null

echo "[boot] h1 resume check …"
"$PY" -c "
import subprocess
import sys
from pathlib import Path
from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

r = Path('$ROOT')
st = str(h1_backtest_status(r).get('status') or 'MISSING')
if is_h1_backtest_sealed(r):
    print('[boot] H1 sealed — skip start')
    sys.exit(0)
if st in ('MISSING', 'FAILED', 'ZOMBIE'):
    print(f'[boot] H1 {st} — native start')
    rc = subprocess.call(
        [sys.executable, 'tools/run_daily_alpha_h1_pipeline.py', '--restart', '--native', '--start-only'],
        cwd=str(r),
    )
    sys.exit(rc)
print(f'[boot] H1 {st} — no start needed')
"

echo "[OK] boot services complete"
