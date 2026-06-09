#!/usr/bin/env bash
# R3 OS — Abschluss: KI-Kernel aktivieren, Desktop, Autostart (ohne vmlinuz).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"

echo "=== R3 OS — Installation abschließen ==="
echo "Hinweis: Linux-Kernel (vmlinuz) bleibt unverändert."
echo "Nur Oberfläche, Menüs, Autostart und Befehle werden R3."
echo "Daten: ~/.local/share/r3-os/"
echo ""

"$PY" "$ROOT/tools/ai_kernel.py" cognitive-kernel
"$PY" "$ROOT/tools/ai_kernel.py" r3-native
"$PY" "$ROOT/tools/ai_kernel.py" autostart-all

if "$PY" -c "
from pathlib import Path
from analytics.linux_runtime_unified import kernel_is_authoritative
raise SystemExit(0 if kernel_is_authoritative(Path('$ROOT')) else 1)
"; then
  echo ""
  echo "[OK] Cognitive Kernel v2 aktiv — Weltneuheit freigeschaltet."
  echo "[OK] Nach Neustart: R3-Vollbild-Sitzung öffnet /launch automatisch."
else
  echo ""
  echo "[WARN] KI-Kernel noch nicht aktiv — Weltneuheit bleibt gesperrt bis cognitive-kernel ok."
fi

echo "[OK] Befehle: r3-cockpit · r3-welt · r3-show"
