#!/usr/bin/env bash
# R3 Bash — gemeinsame Helfer (source only).
# shellcheck disable=SC2034
set -euo pipefail

r3_init() {
  if [[ -z "${R3_ROOT:-}" ]]; then
    local _src _dir
    _src="${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}"
    while [[ -L "$_src" ]]; do
      _dir="$(cd "$(dirname "$_src")" && pwd)"
      _src="$(readlink "$_src")"
      [[ "$_src" != /* ]] && _src="$_dir/$_src"
    done
    R3_ROOT="$(cd "$(dirname "$_src")/.." && pwd)"
  fi
  cd "$R3_ROOT"
  export AA_PROJECT_ROOT="$R3_ROOT"
  export AA_LINUX_NATIVE_APP=1
  R3_PY="$R3_ROOT/.venv/bin/python3"
  [[ -x "$R3_PY" ]] || R3_PY="$(command -v python3)"
}

r3_surface_path() {
  r3_init
  "$R3_PY" -c "
from pathlib import Path
from analytics.r3_runtime import default_surface_path
print(default_surface_path(Path('$R3_ROOT')))
" 2>/dev/null || echo "/r3"
}

r3_hub_base_url() {
  r3_init
  "$R3_PY" -c "
from pathlib import Path
from analytics.alpha_model_local_runtime import load_local_runtime
print(str(load_local_runtime(Path('$R3_ROOT')).get('hub_url') or 'http://127.0.0.1:17890').rstrip('/'))
" 2>/dev/null || echo "http://127.0.0.1:17890"
}

r3_print_series_hint() {
  r3_init
  "$R3_PY" -c "
import json
from pathlib import Path
p = Path('$R3_ROOT') / 'evidence/series_readiness_latest.json'
if not p.is_file():
    raise SystemExit(0)
doc = json.loads(p.read_text(encoding='utf-8'))
mark = 'SERIENREIF' if doc.get('series_ready') else 'OFFEN'
print(' Serienreife:    ' + mark + ' — ' + str(doc.get('readiness_pct') or 0) + '%')
if doc.get('next_de'):
    print(' Nächster Schritt: ' + str(doc.get('next_de')))
" 2>/dev/null || true
}

r3_print_growth_hint() {
  r3_init
  "$R3_PY" -c "
from analytics.r3_local_growth import scan_local_growth
doc = scan_local_growth(__import__('pathlib').Path('$R3_ROOT'), persist=False)
print(' Wachstum:       ' + str(doc.get('headline_de') or '—'))
print(' Nächster Schritt: ' + str(doc.get('next_growth_de') or '—'))
" 2>/dev/null || true
}

r3_print_upgrade_hint() {
  r3_init
  local pending headline profile
  pending="$("$R3_PY" -c "
import json
from pathlib import Path
p = Path('$R3_ROOT') / 'evidence/r3_runtime_upgrade_latest.json'
if not p.is_file():
    raise SystemExit(0)
doc = json.loads(p.read_text(encoding='utf-8'))
pend = doc.get('pending') or {}
if pend.get('status') == 'awaiting_confirmation':
    print(pend.get('label_de') or pend.get('proposal_id') or 'R3-Update')
" 2>/dev/null || true)"
  if [[ -n "$pending" ]]; then
    echo " R3-Update:      BEREIT — $pending"
    echo " Bestätigung:    $(r3_hub_base_url)$(r3_surface_path) → Übernehmen / Später"
  else
    profile="$("$R3_PY" -c "
from analytics.r3_runtime_upgrade import load_runtime_profile
print(load_runtime_profile(__import__('pathlib').Path('$R3_ROOT')).get('label_de') or 'Stabil')
" 2>/dev/null || echo "Stabil")"
    echo " Laufzeitprofil: $profile"
  fi
}
