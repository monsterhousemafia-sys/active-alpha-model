#!/usr/bin/env bash
# Bash — nur GPT-4o (ein Modell). Cloud-Key oder keyless via Ollama.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"

_run_ask() {
  export AA_GPT4O_QUESTION="${1:-}"
  "$PY" -c "
from pathlib import Path
import os, sys
from analytics.bash_gpt4o import bash_gpt4o_ask, format_bash_gpt4o_reply
q = os.environ.get('AA_GPT4O_QUESTION', '').strip()
if not q:
    print('Frage fehlt', file=sys.stderr)
    raise SystemExit(2)
doc = bash_gpt4o_ask(Path('$ROOT'), q)
print(format_bash_gpt4o_reply(doc))
raise SystemExit(0 if doc.get('ok') else 1)
"
}

CMD="${1:-status}"
shift || true

case "$CMD" in
  status|st)
    exec "$PY" -c "
from pathlib import Path
from analytics.bash_gpt4o import bash_gpt4o_status
import sys
doc = bash_gpt4o_status(Path('$ROOT'))
print(doc.get('headline_de', '—'))
print('Modus:', doc.get('mode'), '| Modell:', doc.get('display_model'))
sys.exit(0 if doc.get('ready') else 1)
"
    ;;
  ask|chat|gpt)
    Q="${*:-}"
    _run_ask "$Q"
    ;;
  menu|i)
    "$PY" -c "
from pathlib import Path
from analytics.bash_gpt4o import bash_gpt4o_status
d = bash_gpt4o_status(Path('$ROOT'))
print(d.get('headline_de',''))
print('Frage eingeben (leer = Ende). Modell:', d.get('display_model'))
" || exit 1
    while true; do
      printf "gpt-4o> "
      read -r line || break
      [[ -z "$line" ]] && break
      _run_ask "$line" || true
      echo ""
    done
    ;;
  help|-h|--help)
    cat <<'EOF'
bash_gpt4o.sh — nur GPT-4o im Bash-Cockpit

  status              Bereit? (OpenAI-Key oder Ollama keyless)
  ask <Frage>         Einmalige Antwort
  menu                Interaktiver Chat
  chat <Frage>        Alias für ask

Cloud: OPENAI_API_KEY → echtes gpt-4o
Ohne Key: Ollama qwen2.5:14b als GPT-4o-Berater (keyless)

Safety: keine Orders · Research/Status only
EOF
    ;;
  *)
    echo "Unbekannt: $CMD — bash tools/bash_gpt4o.sh help" >&2
    exit 2
    ;;
esac
