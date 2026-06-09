#!/usr/bin/env bash
# R3-Änderungen sichtbar machen (Cache + 32B-Handoff + Abgleich).
set -euo pipefail
_SELF="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
# shellcheck source=tools/r3_common.sh
source "$(dirname "$_SELF")/r3_common.sh"
r3_init

echo "=============================================="
echo " R3 sichtbar — $(date +%H:%M:%S)"
echo "=============================================="

"$R3_PY" -c "
from pathlib import Path
from analytics.r3_apply_visible import apply_r3_visible_changes
import json
doc = apply_r3_visible_changes(Path('$R3_ROOT'), king_handoff=True)
print(json.dumps(doc, ensure_ascii=False, indent=2))
" || exit 1

OK="$("$R3_PY" -c "
import json
from pathlib import Path
d=json.loads((Path('$R3_ROOT')/'evidence/r3_apply_visible_latest.json').read_text())
print('1' if d.get('ok') and d.get('visible_ui') else '0')
")"

echo "----------------------------------------------"
echo " Oberfläche:     $(r3_hub_base_url)$(r3_surface_path)"
echo " Evidence:       evidence/r3_apply_visible_latest.json"
if [[ "$OK" == "1" ]]; then
  echo " Status:         NEUES UI IM CACHE"
  echo " Browser:        Strg+Shift+R"
else
  echo " Status:         FEHLER — bash tools/king_ops.sh r3-bau gui"
fi
echo " 32B vollständig: bash tools/king_ops.sh r3-bau gui"
echo "=============================================="
[[ "$OK" == "1" ]] || exit 1
