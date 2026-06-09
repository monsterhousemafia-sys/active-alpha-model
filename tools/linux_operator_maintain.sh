#!/usr/bin/env bash
# Level C — Active Alpha maintenance (no sudo).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY=".venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

echo "[C] venv + deps …"
bash tools/setup_linux_native.sh

echo "[C] NVMe symlinks …"
if [[ -x "$PY" ]]; then
  "$PY" -c "
from pathlib import Path
from execution.linux_nvme_storage import repair_migrated_symlinks, apply_nvme_storage_env
import json
r = Path('$ROOT')
print(json.dumps(repair_migrated_symlinks(r), indent=2))
apply_nvme_storage_env(r)
"
fi
bash tools/setup_nvme_storage.sh 2>/dev/null || echo "[C] NVMe offline — lokaler Fallback OK"

echo "[C] batch lock …"
"$PY" -c "
from pathlib import Path
from aa_runtime_profile import cleanup_stale_batch_lock
import json
print(json.dumps(cleanup_stale_batch_lock(Path('$ROOT')), indent=2))
"

echo "[C] price feed state …"
"$PY" -c "
from pathlib import Path
from aa_adaptive_runtime import refresh_price_feed_state
import json
print(json.dumps(refresh_price_feed_state(Path('$ROOT')), indent=2))
"

echo "[C] ready check …"
"$PY" tools/ai_kernel.py ready
echo "[OK] maintain complete"
