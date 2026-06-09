#!/usr/bin/env bash
# R3 lokale App installieren (ein Eintrag — Spiegel der Exekutive).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"
chmod +x "$ROOT/tools/r3_app.sh" "$ROOT/tools/fix_r3_home_ownership.sh" "$ROOT/tools/r3_post_login_hook.sh"
bash "$ROOT/tools/r3_post_login_hook.sh" || true
"$PY" -c "
from pathlib import Path
from analytics.r3_desktop_os import install_r3_exec_mirror_app
import json
print(json.dumps(install_r3_exec_mirror_app(Path('$ROOT')), indent=2, ensure_ascii=False))
"
