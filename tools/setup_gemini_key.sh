#!/usr/bin/env bash
# Gemini API-Key einrichten — Google AI Studio Key für Cloud-Compute (/kombi, /tipp, google-spread).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
export AA_PROJECT_ROOT="$ROOT"

usage() {
  cat <<'EOF'
Gemini API-Key einrichten (Stealth: Keyring oder control/secrets/gemini_api_key)

Key holen: https://aistudio.google.com/apikey

Nutzung:
  bash tools/setup_gemini_key.sh                    # interaktiv (unsichtbar)
  bash tools/setup_gemini_key.sh --from-env         # GEMINI_API_KEY / AA_GEMINI_API_KEY
  bash tools/setup_gemini_key.sh --from-file PATH   # eine Zeile Key
  bash tools/setup_gemini_key.sh AIza...            # Key als Argument
  echo 'AIza...' | bash tools/setup_gemini_key.sh   # stdin
EOF
}

KEY=""
case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  --from-env)
    KEY="${GEMINI_API_KEY:-${AA_GEMINI_API_KEY:-}}"
    ;;
  --from-file)
    if [[ -z "${2:-}" || ! -f "$2" ]]; then
      echo "[FEHLER] --from-file braucht existierenden Pfad"
      exit 1
    fi
    KEY="$(tr -d '\n\r' < "$2")"
    ;;
  "")
    if [[ ! -t 0 ]]; then
      KEY="$(cat)"
    else
      echo "[Gemini] API-Key für Cloud-Compute (Teacher-Student, google-spread)"
      echo "Key holen: https://aistudio.google.com/apikey"
      echo ""
      read -rsp "Gemini API Key (unsichtbar): " KEY
      echo ""
    fi
    ;;
  -*)
    echo "[FEHLER] Unbekannte Option: $1"
    usage
    exit 1
    ;;
  *)
    KEY="$1"
    ;;
esac

KEY="${KEY//[$'\r\n\t ']/}"
if [[ -z "$KEY" ]]; then
  echo "[FEHLER] Kein Key — siehe: bash tools/setup_gemini_key.sh --help"
  exit 1
fi

printf '%s' "$KEY" | "$PY" tools/ai_kernel.py gemini-key-store
"$PY" tools/ai_kernel.py gemini-key-test
echo "[OK] Gemini aktiv — google-spread, /kombi und /tipp nutzen Google Cloud-Compute"
