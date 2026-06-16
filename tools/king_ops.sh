#!/usr/bin/env bash
# König — ein Bash-Einstieg: clean, safe, efficient.
# Usage: bash tools/king_ops.sh <command> [args]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tools/king_safe.sh
source "$ROOT/tools/king_safe.sh"
CMD="${1:-help}"
shift || true

_run() {
  bash "$ROOT/tools/$1" "${@:2}"
}

case "$CMD" in
  status|st)
    _run king_status.sh "$@"
    ;;
  h1|h1-seal|seal)
    _run king_h1_seal.sh "$@"
    ;;
  h1-prep|prep)
    _run king_h1_prep.sh
    ;;
  verify|check)
    _run king_verify.sh "$@"
    ;;
  clean|maintain|maint)
    _run king_clean.sh "$@"
    ;;
  distribute|dist|verteilen)
    _run king_distribute.sh
    ;;
  pulse|puls|könig-puls)
    # shellcheck disable=SC1091
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run king-pulse --force "$@"
    ;;
  setup|32b)
    _run setup_ideal_32b.sh
    ;;
  agent|chat|könig)
    exec bash "$ROOT/tools/alpha_model_agent.sh" "$@"
    ;;
  predict|eod)
    exec bash "$ROOT/tools/linux_live_ops.sh" "$CMD" "$@"
    ;;
  marktanalyse|ma|markt)
    exec bash "$ROOT/tools/marktanalyse_bash.sh" "${1:-start}" "${@:2}"
    ;;
  desktop-finish|32b-desktop)
    exec bash "$ROOT/tools/king_32b_desktop_finish.sh"
    ;;
  local-apps|32b-apps|apps-finish)
    exec bash "$ROOT/tools/king_32b_local_apps_finish.sh"
    ;;
  apps-run|32b-run|lauffähig|lauffaehig)
    export AA_KING_32B_APPS_VERIFY=1
    exec bash "$ROOT/tools/king_32b_local_apps_finish.sh"
    ;;
  h1-fix|32b-h1|h1-repair)
    export AA_KING_32B_H1_VERIFY=1
    exec bash "$ROOT/tools/king_32b_h1_fix.sh"
    ;;
  consolidate|32b-consolidate|apps-consolidate)
    export AA_KING_32B_CONSOLIDATION_VERIFY=1
    exec bash "$ROOT/tools/king_32b_consolidation.sh"
    ;;
  r3-central|32b-r3|central-build|zentrale)
    export AA_KING_32B_R3_CENTRAL_VERIFY=1
    exec bash "$ROOT/tools/king_32b_r3_central.sh"
    ;;
  gui-rebuild|32b-gui|neue-gui)
    exec bash "$ROOT/tools/king_32b_gui_rebuild.sh"
    ;;
  gpt|gpt4o|chat-gpt)
    exec bash "$ROOT/tools/bash_gpt4o.sh" "${1:-menu}" "${@:2}"
    ;;
  connect|h1-connect)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run h1-connect --execute "$@"
    ;;
  workers|h1-workers)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run h1-workers "$@"
    ;;
  learn)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run learn "$@"
    ;;
  watch)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run h1-watch "$@"
    ;;
  pipeline|all)
    _run king_verify.sh
    _run king_clean.sh
    _run king_status.sh
    _run king_h1_seal.sh --wait
    _run king_status.sh
    ;;
  tune)
    _run king_tune.sh "$@"
    ;;
  retire-legacy|retire-benchmark)
    _run king_retire_legacy_benchmark.sh "$@"
    ;;
  nvme|storage|nvme-once)
    bash "$ROOT/tools/nvme_operator_once.sh"
    ;;
  network|netz|takt)
    source "$ROOT/tools/king_common.sh"
    king_init
    _run king_status.sh --json >/dev/null
    king_sync_network bash
    ;;
  alpha-engine|engine-tick|r3-engine)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from analytics.alpha_model_background_engine import tick_alpha_model_background
import json
doc = tick_alpha_model_background(Path('$KING_ROOT'), force=False)
print(doc.get('confirmation_de') or 'Alpha engine tick OK')
print(json.dumps({'ok': doc.get('ok'), 'steps': doc.get('steps_ok')}, ensure_ascii=False))
"
    ;;
  king-trading|32b-trading|trading-assist)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run king-trading "$@"
    ;;
  king-forschung|32b-forschung|forschung-32b)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run king-forschung "$@"
    ;;
  stufe-a|stufe_a|king-stufe-a)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run stufe-a "$@"
    ;;
  stufe-b|stufe_b|king-stufe-b|price-crosscheck)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run stufe-b "$@"
    ;;
  system-update|system_update|update-system)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run system-update "$@"
    ;;
  gemini-key|gemini_key)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run gemini-key "$@"
    ;;
  gemini-key-test|gemini_test)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run gemini-key-test "$@"
    ;;
  freigabe)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_run freigabe "$@"
    ;;
  r3-local|local-first|lokal)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_local_first import apply_r3_local_first, verify_r3_local_first
import json
root = Path('$KING_ROOT')
applied = apply_r3_local_first(root)
verified = verify_r3_local_first(root)
print(applied.get('confirmation_de') or applied.get('headline_de') or 'R3 local-first OK')
print(json.dumps({'ok': verified.get('ok'), 'mirror': applied.get('https_mirror')}, ensure_ascii=False))
"
    ;;
  r3-t212|t212-bond|t212-api)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_t212_api_bond import ensure_r3_t212_api_bond
from analytics.r3_t212_operator_api import resolve_operator_api_state
import json
doc = ensure_r3_t212_api_bond(Path('$KING_ROOT'), persist=True)
doc = {**doc, **resolve_operator_api_state(Path('$KING_ROOT'))}
print(doc.get('headline_de') or doc.get('message_de') or doc.get('confirmation_de') or 'OK')
print(json.dumps({
    'needs_api_setup': doc.get('needs_api_setup'),
    'operator_api_ready': doc.get('operator_api_ready'),
    'setup_ok': doc.get('setup_ok'),
    'bonded': doc.get('bonded'),
    'connected': doc.get('connected'),
    'trusted': doc.get('t212_trusted'),
}, ensure_ascii=False))
"
    ;;
  t212-trust|t212-gate)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root
import json, sys
doc = assess_t212_trust_from_root(Path('$KING_ROOT'), persist=True)
print(doc.get('message_de') or 'T212 Trust')
print(json.dumps({
    'trusted': doc.get('trusted'),
    'orders_allowed': doc.get('orders_allowed'),
    'reason': doc.get('reason_code'),
    'sync_age_s': doc.get('sync_age_s'),
}, ensure_ascii=False))
sys.exit(0 if doc.get('trusted') else 1)
"
    ;;
  t212-trust-report|t212-zahlen)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from analytics.t212_trust_quantified import build_t212_trust_quantified
import json, sys
doc = build_t212_trust_quantified(Path('$KING_ROOT'), persist=True)
print(doc.get('verdict_de') or doc.get('message_de') or 'T212 Trust Report')
for line in doc.get('blockers_de') or []:
    print(' ·', line)
print(json.dumps({
    'trusted': doc.get('trusted'),
    'criteria_passed': sum(1 for c in doc.get('criteria', []) if c.get('passed')),
    'criteria_total': len(doc.get('criteria') or []),
    'measurements': doc.get('measurements'),
}, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('trusted') else 1)
"
    ;;
  swing-theory|swing-theorie|swing)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from analytics.swing_trading_theory_check import run_swing_trading_theory_check
import json, sys
doc = run_swing_trading_theory_check(Path('$KING_ROOT'), persist=True)
print(doc.get('headline_de') or 'Swing-Theorie')
print(json.dumps({'shows_today': doc.get('shows_today'), 'metrics': doc.get('metrics')}, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('shows_today') else 2)
"
    ;;
  fall-watch|fall-wächter|prognosis-fall)
    SUB="${1:-once}"
    shift || true
    case "$SUB" in
      loop|watch)
        exec bash "$ROOT/tools/prognosis_fall_watch.sh" loop
        ;;
      status|stand)
        exec bash "$ROOT/tools/prognosis_fall_watch.sh" status
        ;;
      *)
        exec bash "$ROOT/tools/prognosis_fall_watch.sh" once
        ;;
    esac
    ;;
  forschung-start|forschung)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_forschungszweig import build_forschungszweig_status
from analytics.king_32b_forschung import build_king_32b_forschung_status
from analytics.t212_trust_quantified import build_t212_trust_quantified
import json
root = Path('$KING_ROOT')
king = build_king_32b_forschung_status(root, persist=True)
fz = build_forschungszweig_status(root)
t212 = build_t212_trust_quantified(root, persist=True)
print(fz.get('headline_de') or king.get('headline_de') or 'Forschungsprojekt')
print('T212:', t212.get('verdict_de'))
print(json.dumps({
    'is_forschungsprojekt': king.get('is_forschungsprojekt'),
    'phase': (king.get('growth') or {}).get('phase_de'),
    't212_trusted': t212.get('trusted'),
    't212_blockers': len(t212.get('blockers_de') or []),
}, ensure_ascii=False))
"
    ;;
  t212-sync|t212-learn|t212-lernen)
    SUB="${1:-learn}"
    shift || true
    source "$ROOT/tools/king_common.sh"
    king_init
    case "$SUB" in
      status|stand)
        "$KING_PY" -c "
from pathlib import Path
from analytics.t212_learning_sync import t212_learning_status
import json
doc = t212_learning_status(Path('$KING_ROOT'))
ls = doc.get('last_sync') or {}
print(ls.get('headline_de') or 'T212+Lernen — noch kein Sync')
print(json.dumps({'positions': ls.get('positions_count'), 'cash_eur': ls.get('cash_eur'), 'ok': ls.get('ok')}, ensure_ascii=False))
"
        ;;
      force|sync)
        "$KING_PY" -c "
from pathlib import Path
from analytics.t212_learning_sync import sync_t212_with_learning
import json, sys
doc = sync_t212_with_learning(Path('$KING_ROOT'), force=True, capture_learning=False)
print(doc.get('headline_de') or 'T212 sync OK')
print(json.dumps({'ok': doc.get('ok'), 'positions': doc.get('positions_count')}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
        ;;
      learn|lernen|*)
        "$KING_PY" -c "
from pathlib import Path
from analytics.t212_learning_sync import sync_t212_with_learning
import json, sys
doc = sync_t212_with_learning(Path('$KING_ROOT'), force=True, capture_learning=True)
print(doc.get('headline_de') or 'T212+Lernen OK')
steps = {s.get('step'): s.get('ok') for s in (doc.get('steps') or [])}
print(json.dumps({'ok': doc.get('ok'), 'positions': doc.get('positions_count'), 'steps': steps}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
        ;;
    esac
    ;;
  r3-start|start-r3|ein-klick|one-click)
    source "$ROOT/tools/king_common.sh"
    king_init
    exec "$KING_PY" -c "
from pathlib import Path
from analytics.r3_one_click_start import run_one_click_start
import json, os, sys
doc = run_one_click_start(Path(os.environ.get('AA_PROJECT_ROOT', '$KING_ROOT')), persist=True)
print(doc.get('headline_de') or 'R3 Start')
print(json.dumps({
    'ok': doc.get('ok'),
    'package_ready': doc.get('package_ready'),
    't212_trusted': doc.get('t212_trusted'),
    'notional_eur': doc.get('notional_eur'),
    'cta_de': doc.get('cta_de'),
}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  t212-watch|r3-t212-watch|t212-24-7)
    source "$ROOT/tools/king_common.sh"
    king_init
    exec "$KING_PY" -c "
from pathlib import Path
from analytics.r3_t212_watch import tick_t212_watch
import json, os
doc = tick_t212_watch(Path(os.environ.get('AA_PROJECT_ROOT', '$KING_ROOT')), persist=True)
print(doc.get('headline_de') or 'T212-Watch')
print(json.dumps({'ok': doc.get('ok'), 'skipped': doc.get('skipped'), 'trusted': doc.get('t212_trusted')}, ensure_ascii=False))
"
    ;;
  prognosis|prognose|r3-prognosis)
    SUB="${1:-run}"
    shift || true
    source "$ROOT/tools/king_common.sh"
    king_init
    case "$SUB" in
      status|stand)
        "$KING_PY" -c "
from pathlib import Path
import json
p = Path('$KING_ROOT') / 'evidence/r3_prognosis_pipeline_latest.json'
if p.is_file():
    doc = json.loads(p.read_text())
    print(doc.get('headline_de') or 'Prognose-Pipeline')
    print(json.dumps({'ok': doc.get('ok'), 'trusted': doc.get('t212_trusted'), 'buys': doc.get('worthwhile_buys')}, ensure_ascii=False))
else:
    print('Noch keine Prognose-Freischaltung — bash tools/king_ops.sh prognosis run')
"
        ;;
      run|auto|freischaltung|*)
        "$KING_PY" -c "
from pathlib import Path
from analytics.r3_ops_kernel import run_ops_pipeline
import json, sys
doc = run_ops_pipeline(Path('$KING_ROOT'), phase='prognosis_run', force=True, persist=True, source='king_ops_prognosis')
print(doc.get('headline_de') or 'Prognose OK')
cap = next((s for s in doc.get('steps') or [] if s.get('id') == 'capital'), {})
prog = next((s for s in doc.get('steps') or [] if s.get('id') == 'prognosis'), {})
print(json.dumps({
    'ok': doc.get('ok'),
    'investable_eur': doc.get('investable_eur') or cap.get('investable_eur'),
    'worthwhile_buys': cap.get('worthwhile_buy_count') or doc.get('top_pick_count'),
    'package_ready': prog.get('package_ready'),
    'top_pick_count': doc.get('top_pick_count'),
}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
        ;;
    esac
    ;;
  r3-capital|kontostand|worthwhile)
    SUB="${1:-compute}"
    shift || true
    source "$ROOT/tools/king_common.sh"
    king_init
    case "$SUB" in
      status|stand)
        "$KING_PY" -c "
from pathlib import Path
from analytics.r3_live_capital import sync_live_capital_basis
import json
doc = sync_live_capital_basis(Path('$KING_ROOT'), force=False)
print(doc.get('message_de') or 'Kontostand')
print(json.dumps({'ok': doc.get('ok'), 'cash': doc.get('cash_eur'), 'investable': doc.get('investable_eur')}, ensure_ascii=False))
"
        ;;
      sync|force)
        "$KING_PY" -c "
from pathlib import Path
from analytics.r3_live_capital import sync_live_capital_basis
import json, sys
doc = sync_live_capital_basis(Path('$KING_ROOT'), force=True)
print(doc.get('message_de') or 'Kontostand')
print(json.dumps({'ok': doc.get('ok'), 'cash': doc.get('planning_cash_eur'), 'investable': doc.get('investable_eur')}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
        ;;
      compute|berechnen|*)
        "$KING_PY" -c "
from pathlib import Path
from analytics.r3_live_capital import compute_worthwhile_positions
import json, sys
doc = compute_worthwhile_positions(Path('$KING_ROOT'), force_sync=True)
print(doc.get('headline_de') or doc.get('capital', {}).get('message_de') or 'Kapital')
cap = doc.get('capital_basis') or {}
print(json.dumps({
    'ok': doc.get('ok'),
    'investable_eur': cap.get('investable_eur'),
    'buys': doc.get('worthwhile_buy_count'),
    'sells': doc.get('worthwhile_sell_count'),
}, ensure_ascii=False))
for row in (doc.get('worthwhile_buys') or [])[:6]:
    print(f\"  KAUF {row.get('symbol')}: {float(row.get('gap_eur') or row.get('target_eur') or 0):.0f} € — {str(row.get('action_de') or '')[:60]}\")
sys.exit(0 if doc.get('ok') else 1)
"
        ;;
    esac
    ;;
  r3-activate|profit-activate|gewinn-aktiv)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_profit_activation import activate_after_profit
import json, sys
doc = activate_after_profit(Path('$KING_ROOT'), persist=True)
print(doc.get('headline_de') or 'R3 Aktivierung')
if doc.get('realized_pl_eur') is not None:
    print(f\"Gewinn realisiert: {float(doc['realized_pl_eur']):+.2f} €\")
print(json.dumps({
    'ok': doc.get('ok'),
    'primary_function': doc.get('primary_function'),
    'investable_eur': doc.get('investable_eur'),
    'package_ready': doc.get('package_ready'),
    'new_stocks': len(doc.get('new_stocks') or []),
}, ensure_ascii=False))
for line in (doc.get('recommendations_de') or [])[:5]:
    print('→', line)
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  r3-cycle|trading-cycle|kreislauf)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_trading_cycle import run_trading_cycle
import json
doc = run_trading_cycle(Path('$KING_ROOT'))
print(doc.get('confirmation_de') or doc.get('message_de') or 'Trading-Kreislauf OK')
pm = next((s for s in (doc.get('steps') or []) if s.get('id') == 'postmortem'), {})
if pm.get('voice_warning_de'):
    print('Warnung:', pm.get('voice_warning_de'))
print(json.dumps({'closed': doc.get('closed'), 'cycle_pct': doc.get('cycle_pct')}, ensure_ascii=False))
"
    ;;
  r3-aktuell|r3-refresh-all|r3-voll)
    source "$ROOT/tools/king_common.sh"
    king_init
    FORCE_FLAG="True"
    if [[ "${1:-}" == "--no-force" ]]; then FORCE_FLAG="False"; fi
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_full_refresh import run_r3_full_refresh
import json, sys
doc = run_r3_full_refresh(Path('$KING_ROOT'), force=${FORCE_FLAG}, persist=True)
print(doc.get('headline_de') or 'R3 aktuell')
print('GUI:', doc.get('desktop_url_de'))
for s in doc.get('steps') or []:
    mark = '✓' if s.get('ok') else '✗'
    print(f\"  {mark} {s.get('id')}: {s.get('detail_de') or '—'}\")
print(json.dumps({'ok': doc.get('ok'), 'gui_ok': doc.get('gui_ok'), 'steps_ok': doc.get('steps_ok')}, ensure_ascii=False))
sys.exit(0 if doc.get('gui_ok') else 1)
"
    ;;
  data-care|daten-kernel)
    source "$ROOT/tools/king_common.sh"
    king_init
    FORCE_FLAG="False"
    [[ "${1:-}" == "--force" ]] && FORCE_FLAG="True"
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_ops_kernel import run_ops_pipeline
import json, sys
doc = run_ops_pipeline(Path('$KING_ROOT'), phase='data_care', force=${FORCE_FLAG}, persist=True)
for s in doc.get('steps') or []:
    mark = '✓' if s.get('ok') else '✗'
    print(f\"  {mark} {s.get('id')}: {s.get('detail_de') or '—'}\")
print(doc.get('headline_de') or 'data_care')
print(json.dumps({'ok': doc.get('ok'), 'steps_ok': doc.get('steps_ok')}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  daily-alpha|daily-ops|tages-alpha)
    source "$ROOT/tools/king_common.sh"
    king_init
    PHASE="${1:-pre-us}"
    FORCE_FLAG="False"
    if [[ "${2:-}" == "--force" || "${1:-}" == "--force" ]]; then FORCE_FLAG="True"; fi
    if [[ "${1:-}" == "--force" ]]; then PHASE="pre-us"; fi
    "$KING_PY" -c "
from pathlib import Path
from analytics.daily_alpha_ops import run_daily_alpha_ops
import json, sys
phase = '${PHASE}'.replace('-', '_')
doc = run_daily_alpha_ops(Path('$KING_ROOT'), phase=phase, force=${FORCE_FLAG}, persist=True)
print(doc.get('headline_de') or 'Daily Alpha Ops')
print('Nächster Schritt:', doc.get('next_action_de') or '—')
for s in doc.get('steps') or []:
    mark = '✓' if s.get('ok') else '✗'
    print(f\"  {mark} {s.get('id')}: {s.get('detail_de') or '—'}\")
if doc.get('top_picks'):
    print('Top-Picks:', ', '.join(p.get('symbol','') for p in doc.get('top_picks')[:8]))
print(json.dumps({
    'ok': doc.get('ok'),
    'phase': doc.get('phase'),
    'top_pick_count': doc.get('top_pick_count'),
    'investable_eur': doc.get('investable_eur'),
    'fail_closed': (doc.get('governance') or {}).get('fail_closed'),
}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  daytrading-refresh|datenpflege|daytrading-care)
    source "$ROOT/tools/king_common.sh"
    king_init
    FORCE_FLAG="True"
    if [[ "${1:-}" == "--no-force" ]]; then FORCE_FLAG="False"; fi
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_daytrading_data_care import run_daytrading_data_care
import json, sys
doc = run_daytrading_data_care(Path('$KING_ROOT'), force=${FORCE_FLAG}, persist=True)
print(doc.get('headline_de') or 'Daytrading-Datenpflege')
for s in doc.get('steps') or []:
    mark = '✓' if s.get('ok') else '✗'
    print(f\"  {mark} {s.get('id')}: {s.get('detail_de') or '—'}\")
if doc.get('t212_message_de'):
    print('T212:', doc.get('t212_message_de'))
print(json.dumps({'ok': doc.get('ok'), 'steps_ok': doc.get('steps_ok')}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  r3-quotes|r3-kurse|quotes-refresh|kursaktuell)
    source "$ROOT/tools/king_common.sh"
    king_init
    FORCE_FLAG=""
    if [[ "${1:-}" == "--force" ]]; then FORCE_FLAG="True"; fi
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_quote_keepalive import tick_quote_keepalive
import json, sys
force = ${FORCE_FLAG:-False}
doc = tick_quote_keepalive(Path('$KING_ROOT'), force=force, owner='king_ops', persist=True)
print(doc.get('headline_de') or doc.get('message_de') or 'R3 Kurse')
print(json.dumps({
    'ok': doc.get('ok'),
    'skipped': doc.get('skipped'),
    'price_latest': doc.get('price_latest'),
    'quote_status': (doc.get('assess_after') or {}).get('quote_status'),
}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  erklaer-heute|erklaer_heute|erklär-heute|postmortem|heute)
    source "$ROOT/tools/king_common.sh"
    king_init
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_daily_postmortem import format_postmortem_reply_de, run_daily_postmortem
import json, sys
doc = run_daily_postmortem(Path('$KING_ROOT'), persist=True)
print(format_postmortem_reply_de(doc))
if doc.get('voice_warning_de'):
    print('Sprach-Warnung:', doc.get('voice_warning_de'))
print(json.dumps({'ok': doc.get('ok'), 'bad_day': doc.get('bad_day')}, ensure_ascii=False))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  r3-flow|flow|fluss)
    source "$ROOT/tools/king_common.sh"
    king_init
    king_sync_network bash
    "$KING_PY" -c "
from pathlib import Path
from analytics.r3_flow_orchestrator import sync_r3_flow
import json
doc = sync_r3_flow(Path('$KING_ROOT'), source_node='bash', warm_cache=True, persist=True)
print(doc.get('message_de') or doc.get('headline_de') or 'R3 flow OK')
print(json.dumps({'fluidity_pct': doc.get('fluidity_pct'), 'stable': doc.get('stable')}, ensure_ascii=False))
"
    ;;
  r3-sync|align|abgleich)
    exec bash "$ROOT/tools/r3_sync.sh" "$@"
    ;;
  bau|build|king-bau|bau-pipeline)
    exec bash "$ROOT/tools/king_bau_orchestrator.sh" "$@"
    ;;
  r3-bau|bau-r3|32b-bau)
    exec bash "$ROOT/tools/king_32b_r3_build.sh" "$@"
    ;;
  r3-apply|sichtbar|visible)
    exec bash "$ROOT/tools/r3_apply_visible.sh" "$@"
    ;;
  r3-detach|abnabeln|operational|r3-operational)
    exec bash "$ROOT/tools/r3_operational_detach.sh" "$@"
    ;;
  r3-stealth|community-stealth|verbergen)
    exec bash "$ROOT/tools/r3_community_stealth.sh" "$@"
    ;;
  spread|spread-secure|verteilen-effizient)
    exec bash "$ROOT/tools/spread_ops.sh" "${1:-voll}" "${@:2}"
    ;;
  spread-autonom|spread-autonomous|autonom-spread)
    SUB="${1:-tick}"
    shift || true
    case "$SUB" in
      freigeben|release|enable)
        export AA_SPREAD_AUTONOMOUS_CMD=freigeben
        ;;
      pause|stopp|stop)
        export AA_SPREAD_AUTONOMOUS_CMD=pause
        ;;
      resume|weiter|continue)
        export AA_SPREAD_AUTONOMOUS_CMD=resume
        ;;
      verify|sicherheit|check)
        export AA_SPREAD_AUTONOMOUS_CMD=verify
        ;;
      tick|lauf|run|*)
        export AA_SPREAD_AUTONOMOUS_CMD=tick
        ;;
    esac
    exec "$ROOT/.venv/bin/python3" "$ROOT/tools/ai_kernel.py" spread-autonomous
    ;;
  worker-rewards|entlohnung|legion-entlohnung)
    exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.federation_worker_rewards import build_rewards_summary
import json, os
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = build_rewards_summary(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
"
    ;;
  reddit-post|forum-post|reddit-open)
    exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.reddit_forum_post import open_reddit_submit
from analytics.spread_anonym_policy import is_anonym_enforced, reddit_profile_block
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = reddit_profile_block(r) if is_anonym_enforced(r) else open_reddit_submit(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(2 if doc.get('blocked') else (0 if doc.get('ok') else 1))
"
    ;;
  forum-ack|forum-post-ack|reddit-ack)
    exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.reddit_forum_post import complete_reddit_post
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = complete_reddit_post(r, post_url=os.environ.get('AA_FORUM_POST_URL', ''))
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  tunnel-stable|tunnel|worker-tunnel)
    SUB="${1:-status}"
    shift || true
    case "$SUB" in
      setup|einrichten|open|secure)
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.tunnel_control import tunnel_control_setup
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
wait_s = int(os.environ.get('AA_TUNNEL_LOGIN_WAIT_S', '120'))
doc = tunnel_control_setup(r, wait_s=wait_s)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('tunnel_stable') or doc.get('ok') else 1)
"
        ;;
      login|anmelden)
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.tunnel_stable_provision import open_cloudflare_login
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = open_cloudflare_login(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0)
"
        ;;
      finish|abschliessen|abschließen|provision)
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.tunnel_stable_provision import provision_stable_tunnel
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
wait_s = int(os.environ.get('AA_TUNNEL_LOGIN_WAIT_S', '60'))
doc = provision_stable_tunnel(r, wait_s=wait_s)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') or doc.get('tunnel_stable') else 1)
"
        ;;
      apply|token|anwenden)
        exec "$ROOT/.venv/bin/python3" "$ROOT/tools/ai_kernel.py" spread-tunnel-token
        ;;
      paste|einfuegen)
        exec "$ROOT/.venv/bin/python3" "$ROOT/tools/ai_kernel.py" spread-tunnel-paste
        ;;
      autologin|auto)
        exec bash "$ROOT/tools/cloudflare_tunnel_autologin_setup.sh"
        ;;
      audit|sicherheit)
        exec "$ROOT/.venv/bin/python3" "$ROOT/tools/ai_kernel.py" spread-tunnel-audit
        ;;
      stop|down|kappen|pause|aus)
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.tunnel_control import stop_all_tunnels
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = stop_all_tunnels(r, reason_de='king_ops tunnel-stable stop')
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0)
"
        ;;
      resume|weiter|start)
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.tunnel_control import resume_tunnels
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = resume_tunnels(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0)
"
        ;;
      status|*)
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.tunnel_control import tunnel_control_status
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = tunnel_control_status(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
        ;;
    esac
    ;;
  worker-stability|worker-status|worker-stabilitaet)
    exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.tunnel_control import tunnel_control_status
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = tunnel_control_status(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  spread-finish-anonym|anonym-finish|finish-anonym)
    SUB="${1:-loop}"
    shift || true
    case "$SUB" in
      once|tick|einmal)
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.spread_finish_anonym_loop import run_anonym_finish_tick
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = run_anonym_finish_tick(r, iteration=1)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('done') else 1)
"
        ;;
      status|show)
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.spread_finish_anonym_loop import load_anonym_finish_status
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = load_anonym_finish_status(r)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc else 1)
"
        ;;
      loop|schleife|poll|*)
        INTERVAL="${AA_FINISH_LOOP_INTERVAL_S:-300}"
        MAX_S="${AA_FINISH_LOOP_MAX_S:-86400}"
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.spread_finish_anonym_loop import run_anonym_finish_loop
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
interval_s = int(os.environ.get('AA_FINISH_LOOP_INTERVAL_S', '$INTERVAL'))
max_duration_s = int(os.environ.get('AA_FINISH_LOOP_MAX_S', '$MAX_S'))
doc = run_anonym_finish_loop(r, interval_s=interval_s, max_duration_s=max_duration_s)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('done') else 1)
"
        ;;
    esac
    ;;
  spread-abschluss|spread-finish|spread-complete|abschluss)
    WAIT="${AA_TUNNEL_LOGIN_WAIT_S:-0}"
    exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.spread_completion import run_spread_completion
from analytics.spread_anonym_policy import is_anonym_enforced
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
wait_s = int(os.environ.get('AA_TUNNEL_LOGIN_WAIT_S', '$WAIT'))
anonym = is_anonym_enforced(r)
doc = run_spread_completion(r, wait_tunnel_s=wait_s, anonym=anonym)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('done') else 1)
"
    ;;
  local-control|kontrolle|uebernimm|übernimm|lokal)
    SUB="${1:-repair}"
    shift || true
    case "$SUB" in
      status|show|*)
        REPAIR=0
        [[ "$SUB" == repair* || "$SUB" == übernimm* || "$SUB" == uebernimm* ]] && REPAIR=1
        exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.local_control import assume_local_control
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
repair = os.environ.get('AA_LOCAL_CONTROL_REPAIR', '${REPAIR:-1}') not in ('0', 'false', 'no')
doc = assume_local_control(r, repair=repair)
print(json.dumps(doc, ensure_ascii=False, indent=2))
sys.exit(0 if doc.get('ok') else 1)
"
        ;;
    esac
    ;;
  spread-internet|internet-spread|oeffentlich)
    exec bash "$ROOT/tools/spread_ops.sh" internet "$@"
    ;;
  google-spread|spread-google|google-welt|welt-google)
    exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.google_world_spread import run_google_world_spread
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = run_google_world_spread(r, use_gemini=True, force_export=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
exit_ok = doc.get('spread_ok') or doc.get('copy_ok')
sys.exit(0 if exit_ok else 1)
"
    ;;
  legitimate-ops|legit-ops|legit-check|ops-legit)
    REFRESH="${1:-}"
    shift || true
    REFRESH_Q="False"
    [[ "$REFRESH" == "--quotes" || "$REFRESH" == "--force-quotes" ]] && REFRESH_Q="True"
    exec "$ROOT/.venv/bin/python3" -c "
from pathlib import Path
from analytics.legitimate_ops_check import run_legitimate_ops_check
import json, os, sys
r = Path(os.environ.get('AA_PROJECT_ROOT', '$ROOT'))
doc = run_legitimate_ops_check(r, refresh_quotes=${REFRESH_Q}, run_spread=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
print(doc.get('headline_de') or '—')
for k, p in (doc.get('pillars') or {}).items():
    mark = '✓' if p.get('ok') else '✗'
    print(f'  {mark} {k}: {p.get(\"message_de\") or \"—\"}')
sys.exit(0 if doc.get('ok') else 1)
"
    ;;
  community-spread|ausbreitung|linux-community)
    exec bash "$ROOT/tools/spread_ops.sh" voll "$@"
    ;;
  lan-spread|festnetz|telefonkabel|lan)
    exec bash "$ROOT/tools/spread_ops.sh" haus "$@"
    ;;
  lan-usb|usb-worker|haus-deploy)
    exec bash "$ROOT/tools/lan_usb_deploy.sh" "$@"
    ;;
  usb-segnen|usb-seal|usb-bless|usb-abnahme)
    TARGET="${1:-$ROOT}"
    shift || true
    exec bash "$ROOT/tools/usb_portable_bless.sh" "$TARGET" "${*:-}"
    ;;
  usb-verabschieden|usb-farewell|usb-tschuess|klon-verabschieden)
    MOUNT="${1:-/run/media/machinax7/USB Stick}"
    exec bash "$ROOT/tools/usb_portable_farewell.sh" "$MOUNT"
    ;;
  broadcast|verbreiten|alle|jeder)
    exec bash "$ROOT/tools/spread_ops.sh" voll "$@"
    ;;
  haus-zur-welt|haus-welt|welt|world)
    exec bash "$ROOT/tools/spread_ops.sh" welt "$@"
    ;;
  whatsapp|whatsapp-spread|wa-spread)
    case "${1:-verify}" in
      terminal|alles|all-terminal)
        shift || true
        exec bash "$ROOT/tools/whatsapp_terminal_all.sh" "${1:-all}" "${@:2}"
        ;;
      terminal-beenden|terminal-finish|terminal-stop)
        exec bash "$ROOT/tools/whatsapp_terminal_all.sh" finish
        ;;
      *)
        exec bash "$ROOT/tools/whatsapp_spread.sh" "${1:-verify}" "${@:2}"
        ;;
    esac
    ;;
  glasfaser|glasfaser-offline|fiber|faser|bagger|notfall)
    exec bash "$ROOT/tools/glasfaser_offline.sh" "$@"
    ;;
  erhaltung|erhaltungsprogramm|conservation|bash-welt)
    exec bash "$ROOT/tools/erhaltungsprogramm.sh" "$@"
    ;;
  linux-potential|linux-full|linux)
    exec bash "$ROOT/tools/linux_potential.sh" "$@"
    ;;
  series-ready|serienreife|series)
    exec bash "$ROOT/tools/series_readiness.sh" "$@"
    ;;
  cockpit-update|decision-cockpit|vision-update)
    exec bash "$ROOT/tools/decision_cockpit_update.sh" "$@"
    ;;
  r3-checklist|checklist)
    exec bash "$ROOT/tools/r3_checklist.sh" "$@"
    ;;
  system-audit|audit|system)
    exec bash "$ROOT/tools/system_audit.sh" "$@"
    ;;
  reboot-apply|neustart|reboot-full)
    exec bash "$ROOT/tools/reboot_full_apply.sh" "$@"
    ;;
  watch-bg)
    source "$ROOT/tools/king_common.sh"
    king_init
    if king_h1_sealed; then echo "[watch] bereits sealed"; exit 0; fi
    if king_csv_ready; then _run king_h1_seal.sh; exit $?; fi
    if king_watch_bg_running; then
      echo "[watch] läuft bereits PID $(cat "$ROOT/.active_alpha_jobs/h1_watch_bg.pid")"
      exit 0
    fi
    if ! king_benchmark_running; then echo "[watch] kein Benchmark — starte h1-seal" >&2; _run king_h1_seal.sh; exit $?; fi
    king_with_lock h1_watch_bg bash -c "
      nohup bash '$ROOT/tools/king_h1_seal.sh' --wait >>'$ROOT/evidence/king_h1_watch.log' 2>&1 &
      echo \$! >'$ROOT/.active_alpha_jobs/h1_watch_bg.pid'
    "
    echo "[watch] Hintergrund PID $(cat "$ROOT/.active_alpha_jobs/h1_watch_bg.pid") — log: evidence/king_h1_watch.log"
    ;;
  benchmark)
    source "$ROOT/tools/king_common.sh"
    king_init
    if king_benchmark_running; then
      echo "[benchmark] läuft bereits PID $(king_benchmark_pid) — kein Zweitstart" >&2
      exit 3
    fi
    king_with_lock h1_benchmark bash -c "
      cd '$ROOT' && '$ROOT/.venv/bin/python3' tools/generate_h1_naive_benchmark.py --wait
    "
    ;;
  help|-h|--help|*)
    cat <<'EOF'
king_ops.sh — König Bash-Orchestrator

  verify              Fail-closed Safety-Checks
  status              Snapshot (PID, CSV, Seal, hung)
  h1-seal             Benchmark → h1-watch (ein Job)
  h1-prep             NVMe+GPU+Ollama-Prep (kein Benchmark)
  clean               Projekt-Müll + Locks (pycache, Logs, Zips, Pilot-Stale)
  distribute          Spread/Tunnel/Worker (king_distribute.sh)
  pulse               König-Puls (ai_kernel)
  setup               Ideal-32B + Ollama
  agent               alpha-model-agent starten
  predict | eod       linux_live_ops (fail-closed)
  marktanalyse | ma   Bash-Cockpit (ehemalige Marktanalyse)
  desktop-finish      32B build-kernel — Desktop fertigstellen
  local-apps          32B — Apps audit (überspringt build wenn alles OK)
  apps-run            32B build-kernel — alle Apps prüfen + lauffähig machen
  h1-fix              32B build-kernel — H1-assoziierte Fehler beheben
  consolidate         32B — App-Konsolidierung (GPU/RAM, weniger Redundanz)
  r3-central          32B — R3 als zentrale Quelle (Feeds, /api/r3/central, /desktop)
  alpha-engine        Active Alpha Hintergrund (Prognose, Rebalance-Plan, H1-Monitor)
  r3-local            Lokal wirksam + eine HTTPS-Spiegelung (Duplikate eliminieren)
  r3-t212             Trading212 API-Bond sync + Bestätigung (GET /api/r3/t212)
  t212-trust          T212 Trust Gate — fail-closed Status (Orders/Plan)
  t212-sync           T212↔Modell: status|force (nur API) | learn (Sync+Ledger+Outcomes)
  r3-start            Ein-Klick-Start: T212+Prognose+Paket (R3 «Start»-Button)
  t212-watch          24/7 T212-Watch-Tick (Timer, coalesced)
  prognosis           Prognose-Freischaltung: run|status (Live-Cash→Prognose→Funktionen)
  r3-capital          Live-Kontostand: sync|status|compute (lohnende Käufe/Umschichtung)
  r3-activate         Nach Gewinn: Sync+Plan+neue Aktien+Funktionen+Analyse
  freigabe            R3-Freigabe vorbereiten (Gutachter + Paket, nur User-Order)
  r3-quotes           Kurse frisch halten (Ingest + Live-Quotes, coalesced)
  r3-cycle            Geschlossener Trading-Kreislauf (Internet→T212-Sync→Prognose→Postmortem)
  r3-aktuell          R3 vollständig (Hub+GUI-Cache+Mirror+Daytrading-Daten)
  daily-alpha         Tages-Alpha-Ops: pre-us|intraday|eod|full (--force)
  daytrading-refresh  Datenpflege Daytrading (Kurse→Snapshot→Kreislauf→Learning)
  erklaer-heute       Read-only Tagesbilanz Plan vs. SPY (/erklär-heute im R3-Chat)
  r3-flow             Hard/Soft-Orchestrator → R3 Desktop (Fluss-Streifen, Cache)
  r3-sync | align     Hub + Profil + Upgrade-Scan + Cache + Stack (fein abstimmen)
  bau | build         Bau-Pipeline: verify → 32B build → sync → pytest → Evidence
  r3-bau | bau-r3     König 32B autonom: R3-Bau (Mandat → build-kernel → r3_sync)
  r3-apply | sichtbar  UI-Änderungen sichtbar (Cache + 32B-Handoff + Abgleich)
  r3-detach | abnabeln R3-Laufzeit ohne Cursor (Install + Hub + Stack + Evidence)
  r3-stealth | verbergen Community-Stealth-Autostart (Hidden, Hub-only, systemd)
  spread | verteilen-effizient verify|haus|welt|voll|internet (fail-closed)
  tunnel-stable setup|login|finish|paste|status  stabile Join-URL (Cloudflare Token)
  worker-stability  Hub/Tunnel/Worker-Status (evidence/worker_stability_latest.json)
  local-control repair|status  Ubuntu-Runtime unter king_ops (Hub/Tunnel/Worker)
  spread-internet | oeffentlich Internet-Spread ausbauen (/join + Forum + Welt-ZIP)
  whatsapp terminal|alles  install + durch | terminal beenden (Aufgabe abschließen)
  whatsapp setup|auto-setup|verify|shield|durch (Auto-Send ohne Docker)
  lan-usb | haus-deploy ZIP auf USB (--usb) oder LAN (--lan) — nur Haus/LAN
  glasfaser | faser Glasfaser-Umzug 3-Phasen (--init --repair --go-offline --comeback)
  erhaltung | bash-welt Erhaltungsprogramm + Bash-Welt-Konsolidierung (--start)
  linux-potential     Linux scan/apply — NVMe, v2, Ollama, R3-Align (ohne sudo)
  series-ready        Serienreife-Gate — lokales R3 betriebsbereit (scan/--repair)
  cockpit-update      R3 ↔ Decision-Cockpit-Vision (Snapshot + Bridge + --gui-rebuild)
  r3-checklist        Betriebs-Checkliste A–G scannen (--repair)
  system-audit        Umfassendes Audit — Safety, Stack, R3, Serienreife (--tests)
  reboot-apply        Neustart-Vorbereitung / --reboot (D) / --post nach Login
  gui-rebuild         32B build-kernel — neue einheitliche GUI (alle Oberflächen)
  gpt | gpt4o         Bash — nur GPT-4o (ein Modell)
  connect             h1-connect --execute
  workers             h1-workers Status
  learn | watch       Kernel-Slash
  benchmark           nur mom_1 Benchmark (flock)
  pipeline            status → maintain → h1-seal → status
  tune                verify + clean + governance + watch-bg
  retire-legacy       Legacy-Benchmark prüfen/beenden (über ETA, kein CSV)
  nvme                NVMe-Datentier migrieren (setup_nvme_storage.sh)
  network             Netzwerk-Takt synchronisieren (status + pulse)
  watch-bg            H1-Watch im Hintergrund (Benchmark läuft)

Beispiel:
  bash tools/king_ops.sh tune
  bash tools/king_ops.sh pipeline
EOF
    ;;
esac
