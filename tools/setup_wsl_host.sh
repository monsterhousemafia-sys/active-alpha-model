#!/usr/bin/env bash
# One-time WSL host setup: native repo copy (NOT /mnt/e for compute), venv, caches, smoke test.
# Invoked via: bash tools/wsl_conductor.sh setup
set -euo pipefail

WIN_SRC="${WIN_SRC:-/mnt/e/active_alpha_model}"
WSL_ROOT="${WSL_ROOT:-$HOME/active_alpha_model}"
PY="${PY:-python3}"
REPORT_DIR="${WSL_ROOT}/evidence/r0_migration"
REPORT="${REPORT_DIR}/wsl_setup_report.json"

log() { echo "[wsl-setup] $*"; }

log "source=$WIN_SRC dest=$WSL_ROOT"

if [[ ! -d "$WIN_SRC" ]]; then
  log "ERROR: Windows repo not found at $WIN_SRC"
  log "Set WIN_SRC if drive letter differs, e.g. WIN_SRC=/mnt/d/active_alpha_model"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip rsync git

mkdir -p "$(dirname "$WSL_ROOT")"
RSYNC_EX=(
  --exclude '.venv'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.git/objects'
)

if [[ ! -d "$WSL_ROOT/.git" ]] && [[ ! -f "$WSL_ROOT/active_alpha_model.py" ]]; then
  log "rsync repo into WSL native filesystem (fast I/O)..."
  rsync -a --delete "${RSYNC_EX[@]}" "$WIN_SRC/" "$WSL_ROOT/"
else
  log "repo exists — incremental rsync..."
  rsync -a "${RSYNC_EX[@]}" "$WIN_SRC/" "$WSL_ROOT/"
fi

cd "$WSL_ROOT"
chmod +x tools/*.sh 2>/dev/null || true

if [[ ! -d .venv ]]; then
  log "creating venv..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements_active_alpha.txt

log "syncing shared cache (~500MB, may take a few minutes)..."
mkdir -p robustness_results_trading212/_shared_cache validation_runs control/r0_migration evidence/r0_migration
if [[ -d "$WIN_SRC/robustness_results_trading212/_shared_cache" ]]; then
  rsync -a "$WIN_SRC/robustness_results_trading212/_shared_cache/" \
    robustness_results_trading212/_shared_cache/
fi

log "seeding validation run artifacts from Windows..."
for d in "$WIN_SRC"/validation_runs/*_M1_MOM_BLEND_MATCHED_CONTROLS; do
  [[ -d "$d" ]] || continue
  base="$(basename "$d")"
  mkdir -p "validation_runs/$base"
  for f in prediction_cache.pkl prediction_cache_meta.json strategy_daily_returns.csv integrity_report.json path_sim_checkpoint.pkl; do
    [[ -f "$d/$f" ]] && cp -f "$d/$f" "validation_runs/$base/" || true
  done
done
for v in R0_LEGACY_ENSEMBLE R3_w075_q065_noexit; do
  latest="$(ls -d "$WIN_SRC"/validation_runs/*_"$v" 2>/dev/null | sort | tail -1 || true)"
  [[ -n "$latest" && -f "$latest/strategy_daily_returns.csv" ]] || continue
  base="$(basename "$latest")"
  mkdir -p "validation_runs/$base"
  cp -f "$latest/strategy_daily_returns.csv" "validation_runs/$base/" 2>/dev/null || true
  cp -f "$latest/integrity_report.json" "validation_runs/$base/" 2>/dev/null || true
done

log "compile + import smoke..."
python -c "from execution.linux_security_boundary import apply_linux_compute_env; apply_linux_compute_env(overwrite=True)"
python -c "import ast; ast.parse(open('tools/run_validation_matrix.py').read())"
python -c "import ast; ast.parse(open('tools/_m1_autoseal.py').read())"
python -c "from tools import r0_migration_hw; print('hw nproc=', r0_migration_hw.nproc())"
python tools/preflight_wsl_migration.py --json >/dev/null

log "wsl status snapshot..."
python tools/r0_migration_status.py > "$REPORT_DIR/wsl_status_after_setup.json" || true

READY="$WSL_ROOT/.wsl_host_ready"
cat > "$READY" <<EOF
ready_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
win_src=$WIN_SRC
wsl_root=$WSL_ROOT
cpu_cores=$(nproc)
EOF

mkdir -p "$REPORT_DIR"
python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
import os

root = Path(os.environ.get("WSL_ROOT", str(Path.home() / "active_alpha_model")))
win_src = os.environ.get("WIN_SRC", "/mnt/e/active_alpha_model")
report_path = root / "evidence" / "r0_migration" / "wsl_setup_report.json"
ready = (root / ".wsl_host_ready").read_text(encoding="utf-8").strip() if (root / ".wsl_host_ready").is_file() else ""
report = {
    "setup_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "wsl_root": str(root),
    "win_src": win_src,
    "cpu_cores": os.cpu_count() or 0,
    "ready_marker": ready,
}
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
PY

echo ""
echo "===== WSL HOST READY ====="
echo "  cd $WSL_ROOT"
echo "  bash tools/wsl_conductor.sh status"
echo "  bash tools/wsl_conductor.sh autoseal    # poll + seal + M2"
echo "  bash tools/wsl_conductor.sh m1          # resume matrix if needed"
echo ""
echo "Report: $REPORT"
