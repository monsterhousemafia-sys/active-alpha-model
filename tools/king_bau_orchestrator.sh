#!/usr/bin/env bash
# König-Bau-Pipeline — Preflight → Bau → Verify → pytest → Evidence
# Usage:
#   bash tools/king_bau_orchestrator.sh [topic]
#   bash tools/king_bau_orchestrator.sh --dry-run [topic]
#   bash tools/king_bau_orchestrator.sh --prep [topic]
set -euo pipefail
# shellcheck source=tools/king_common.sh
source "$(cd "$(dirname "$0")" && pwd)/king_common.sh"
king_assert_project_root

TOPIC=""
DRY_RUN=0
PREP=0
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    --prep|--stufe-a) PREP=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: king_bau_orchestrator.sh [--dry-run] [--prep] [topic]
Topics: r3, desktop, gui, apps, h1, stufe-a, prognose
Via king_ops: bash tools/king_ops.sh bau [--prep] [topic]
EOF
      exit 0
      ;;
    -*) echo "[bau] Unbekannte Option: $arg" >&2; exit 2 ;;
    *) TOPIC="$arg" ;;
  esac
done

LOG="$KING_ROOT/evidence/king_bau_orchestrator.log"
mkdir -p "$(dirname "$LOG")"
echo "[bau] $(date -u +%Y-%m-%dT%H:%M:%SZ) topic=${TOPIC:-r3} dry=$DRY_RUN prep=$PREP" | tee -a "$LOG"

if [[ "$DRY_RUN" -eq 1 ]]; then
  exec "$KING_PY" -c "
from pathlib import Path
from analytics.king_bau_pipeline import build_bau_plan, write_bau_evidence
import json
root = Path('$KING_ROOT')
plan = build_bau_plan(root, topic='$TOPIC', prep_stufe_a=$PREP)
plan['ok'] = True
plan['dry_run'] = True
plan['headline_de'] = 'Dry-run — kein Bau ausgeführt'
write_bau_evidence(root, plan)
print(json.dumps(plan, indent=2, ensure_ascii=False))
"
fi

ROUTE="$("$KING_PY" -c "
from pathlib import Path
from analytics.king_bau_pipeline import resolve_bau_route
print(resolve_bau_route(Path('$KING_ROOT'), '$TOPIC'))
")"
echo "[bau] Route: $ROUTE" | tee -a "$LOG"

FAIL=0
STEPS_FILE="$KING_LOCK_DIR/king_bau_steps.json"
echo "[]" >"$STEPS_FILE"

_step_record() {
  local id="$1" label="$2" ok="$3"
  "$KING_PY" -c "
import json
from pathlib import Path
p = Path('$STEPS_FILE')
steps = json.loads(p.read_text(encoding='utf-8'))
steps.append({'id': '$id', 'label_de': '''$label''', 'ok': '$ok' == '1'})
p.write_text(json.dumps(steps, ensure_ascii=False), encoding='utf-8')
"
}

_step_run() {
  local id="$1" label="$2"
  shift 2
  echo "[bau] ▶ $label" | tee -a "$LOG"
  if "$@" >>"$LOG" 2>&1; then
    _step_record "$id" "$label" 1
  else
    _step_record "$id" "$label" 0
    FAIL=1
  fi
}

_bau_run() {
  _step_run preflight_verify "Preflight verify" bash "$KING_ROOT/tools/king_verify.sh" || true

  if "$KING_PY" "$KING_ROOT/tools/ai_kernel.py" llm-health >/dev/null 2>&1; then
    _step_record llm_health "Ollama bereit" 1
    echo "[bau] ▶ Ollama bereit" | tee -a "$LOG"
  else
    _step_record llm_health "Ollama bereit" 0
    echo "[bau] WARN — Ollama nicht bereit" | tee -a "$LOG"
  fi

  if [[ "$PREP" -eq 1 ]]; then
    _step_run stufe_a "Stufe A prep" bash "$KING_ROOT/tools/king_ops.sh" stufe-a --force || true
  fi

  case "$ROUTE" in
    r3-bau)       _step_run build "R3 Bau (32B)" bash "$KING_ROOT/tools/king_32b_r3_build.sh" "$TOPIC" ;;
    desktop-finish) _step_run build "Desktop finish" bash "$KING_ROOT/tools/king_32b_desktop_finish.sh" ;;
    gui-rebuild)  _step_run build "GUI rebuild" bash "$KING_ROOT/tools/king_32b_gui_rebuild.sh" ;;
    apps-run)     _step_run build "Apps run" bash "$KING_ROOT/tools/king_32b_local_apps_finish.sh" ;;
    h1-fix)       _step_run build "H1 fix" bash "$KING_ROOT/tools/king_32b_h1_fix.sh" ;;
    stufe-a)      _step_run build "Stufe A" bash "$KING_ROOT/tools/king_ops.sh" stufe-a --force ;;
    *)            _step_run build "R3 Bau default" bash "$KING_ROOT/tools/king_32b_r3_build.sh" "$TOPIC" ;;
  esac

  _step_run r3_sync "R3 sync" bash "$KING_ROOT/tools/r3_sync.sh" --repair || true
  _step_run verify_post "Post verify" bash "$KING_ROOT/tools/king_verify.sh" || true

  PYTEST_JSON="$("$KING_PY" -c "
from pathlib import Path
from analytics.king_bau_pipeline import run_safe_pytest
import json
print(json.dumps(run_safe_pytest(Path('$KING_ROOT')), ensure_ascii=False))
")"
  echo "[bau] pytest: $PYTEST_JSON" | tee -a "$LOG"
  if echo "$PYTEST_JSON" | "$KING_PY" -c "import json,sys; sys.exit(0 if json.load(sys.stdin).get('ok') else 1)"; then
    _step_record pytest "Safe pytest" 1
  else
    _step_record pytest "Safe pytest" 0
    FAIL=1
  fi

  king_sync_network bash || true
  _step_record network "Network pulse" 1

  HEADLINE="$("$KING_PY" -c "
from pathlib import Path
import json
from analytics.king_bau_pipeline import write_bau_evidence
steps = json.loads(Path('$STEPS_FILE').read_text(encoding='utf-8'))
fail = int('$FAIL')
doc = {
    'ok': fail == 0,
    'topic': '$TOPIC',
    'route': '$ROUTE',
    'prep_stufe_a': $PREP == 1,
    'steps': steps,
    'headline_de': 'Bau-Pipeline OK' if fail == 0 else 'Bau-Pipeline teilweise/fehlgeschlagen',
    'log_ref': 'evidence/king_bau_orchestrator.log',
}
write_bau_evidence(Path('$KING_ROOT'), doc)
print(doc['headline_de'])
")"
  echo "[bau] $HEADLINE" | tee -a "$LOG"
  return "$FAIL"
}

king_with_lock king_bau_orchestrator _bau_run
exit $?
