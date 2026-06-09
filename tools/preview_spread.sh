#!/usr/bin/env bash
# Community-Verbreitung — Text + Share-URLs ausgeben.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_LINUX_NATIVE_APP=1
export AA_PROJECT_ROOT="$ROOT"

"$PY" "$ROOT/tools/preview_hub.py" --ensure 2>/dev/null || true

"$PY" -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '$ROOT')
from analytics.preview_federation import build_share_package
from analytics.preview_manifest import load_preview_manifest
r = Path('$ROOT')
pkg = build_share_package(r)
mf = load_preview_manifest(r)
print('=== ACTIVE ALPHA — LINUX COMMUNITY ===')
print(mf.get('one_liner_de') or '')
print()
print('Hub:   ', pkg.get('share_url'))
print('Join:  ', pkg.get('join_url'))
print('Export: ai_kernel preview-export')
print()
print('Volltext: docs/LINUX_COMMUNITY_DE.md')
print('Aufklärung im Hub beim ersten Besuch (Pflichtlektüre).')
"
