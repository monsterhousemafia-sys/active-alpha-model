#!/usr/bin/env bash
# Neustart — Vorbereitung, Reboot (D), Post-Boot-Hinweis.
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
# shellcheck source=tools/r3_common.sh
source "$ROOT/tools/r3_common.sh"
r3_init
PY="$R3_PY"

REBOOT=0
POST=0
for arg in "$@"; do
  case "$arg" in
    --reboot) REBOOT=1 ;;
    --post) POST=1 ;;
    -h|--help)
      cat <<'EOF'
reboot_full_apply.sh — Neustart mit vollständiger Wirksamkeit

  (ohne Flags)     Vorbereitung: R3-Align, Stack, Linux, Serienreife, Audit
  --reboot         Vorbereitung + System-Neustart (Level D)
  --post           Post-Boot-Verifikation (nach Login)

Ablauf:
  bash tools/reboot_full_apply.sh
  AA_OPERATOR_APPROVE_D=1 bash tools/reboot_full_apply.sh --reboot
  # nach Login automatisch via Autostart — oder manuell:
  bash tools/reboot_full_apply.sh --post

EOF
      exit 0
      ;;
  esac
done

if [[ "$POST" -eq 1 ]]; then
  echo "=============================================="
  echo " Post-Boot Apply — $(date +%H:%M:%S)"
  echo "=============================================="
  "$PY" -c "
from pathlib import Path
from analytics.reboot_full_apply import complete_after_reboot
import json
doc = complete_after_reboot(Path('$ROOT'))
print(json.dumps(doc, ensure_ascii=False, indent=2))
"
  exit 0
fi

echo "=============================================="
echo " Neustart-Vorbereitung — $(date +%H:%M:%S)"
echo "=============================================="

"$PY" -c "
from pathlib import Path
from analytics.reboot_full_apply import prepare_before_reboot
import json
doc = prepare_before_reboot(Path('$ROOT'))
print(json.dumps({
    'ok': doc.get('ok'),
    'headline_de': doc.get('headline_de'),
    'series_ready': doc.get('series_ready'),
    'audit_ok': doc.get('audit_ok'),
    'autostart': doc.get('autostart'),
    'steps': [{'id': s.get('id'), 'ok': s.get('ok')} for s in doc.get('steps') or []],
}, ensure_ascii=False, indent=2))
" || exit 1

if [[ "$REBOOT" -eq 0 ]]; then
  echo "----------------------------------------------"
  echo " Vorbereitung fertig. Neustart:"
  echo "   AA_OPERATOR_APPROVE_D=1 bash tools/reboot_full_apply.sh --reboot"
  echo " Evidence:       evidence/reboot_apply_pending.json"
  echo "=============================================="
  exit 0
fi

if [[ "${AA_OPERATOR_APPROVE_D:-}" != "1" ]]; then
  echo "[FEHLER] Reboot braucht: AA_OPERATOR_APPROVE_D=1" >&2
  exit 2
fi

echo "----------------------------------------------"
echo " Reboot in 8s — Ctrl+C zum Abbrechen"
echo " Nach Login: Autostart + Post-Boot Apply"
echo "=============================================="
sleep 8
exec bash "$ROOT/tools/linux_operator_system.sh" reboot --approve
