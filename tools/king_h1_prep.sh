#!/usr/bin/env bash
# H1 Hard/Soft-Prep — NVMe-Env, Ollama-Unload, GPU-Returns, Netzwerk-Pulse (kein Benchmark-Start).
# Usage: bash tools/king_h1_prep.sh
set -euo pipefail
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_assert_project_root

export AA_H1_UNLOAD_OLLAMA="${AA_H1_UNLOAD_OLLAMA:-1}"
export AA_H1_GPU_RETURNS="${AA_H1_GPU_RETURNS:-1}"

echo "=============================================="
echo " H1 NETZWERK-PREP — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================="

"$KING_PY" -c "
from pathlib import Path
from analytics.h1_network_prep import run_h1_network_prep
import json
doc = run_h1_network_prep(Path('$KING_ROOT'), phase='execute')
print(json.dumps({
    'headline': doc.get('headline_de'),
    'gpu_ready': doc.get('gpu_ready'),
    'nvme': doc.get('nvme_mounted'),
    'blockers': doc.get('blockers_de'),
    'next': doc.get('next_action_de'),
}, indent=2, ensure_ascii=False))
"

echo "----------------------------------------------"
echo " Evidence: evidence/h1_network_prep_latest.json"
echo " Nächster Schritt: bash tools/king_ops.sh h1-seal"
echo "=============================================="
