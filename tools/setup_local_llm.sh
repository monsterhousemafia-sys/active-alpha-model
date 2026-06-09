#!/usr/bin/env bash
# Stufe 3 — Ollama installieren, Modell laden, Chat-Verknüpfung.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
MODEL="${AA_LOCAL_LLM_MODEL:-qwen2.5:7b}"
BIN_DIR="${HOME}/.local/bin"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
DESKTOP="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$BIN_DIR" "$DESKTOP"

install_ollama() {
  if command -v ollama >/dev/null 2>&1; then
    echo "[OK] Ollama bereits installiert: $(ollama --version 2>/dev/null || ollama -v)"
    return 0
  fi
  if [[ -x "${HOME}/.local/share/ollama/bin/ollama" ]]; then
    ln -sf "${HOME}/.local/share/ollama/bin/ollama" "${HOME}/.local/bin/ollama"
    echo "[OK] Ollama user-local: ${HOME}/.local/share/ollama/bin/ollama"
    return 0
  fi
  if command -v curl >/dev/null 2>&1; then
    echo "[D] Installiere Ollama (system) …"
    curl -fsSL https://ollama.com/install.sh | sh && return 0
  fi
  echo "[D] curl fehlt — user-local Setup …"
  bash "$(dirname "$0")/setup_local_llm_user.sh"
}

start_ollama() {
  if curl -sf --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "[OK] Ollama API läuft"
    return 0
  fi
  if systemctl is-active ollama >/dev/null 2>&1; then
    sleep 2
    return 0
  fi
  if command -v ollama >/dev/null 2>&1; then
    echo "[INFO] Starte ollama serve im Hintergrund …"
    nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
    sleep 3
  fi
}

pull_model() {
  echo "[INFO] Lade Modell $MODEL (RTX 3090 / 60GB — kann einige Minuten dauern) …"
  ollama pull "$MODEL"
}

write_launchers() {
  chmod +x "$ROOT/tools/active_alpha_chat.py"
  ln -sf "$ROOT/tools/active_alpha_chat.py" "$BIN_DIR/active-alpha-chat"
  cat >"$DESKTOP/Active-Alpha-Chat.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Active Alpha Chat (lokal)
Comment=Stufe 3 — Auto ohne Cursor (Ollama)
Exec=gnome-terminal -- bash -c 'cd $ROOT && $PY tools/active_alpha_chat.py; exec bash'
Path=$ROOT
Icon=utilities-terminal
Terminal=true
Categories=Development;Finance;
Keywords=active-alpha;chat;auto;
EOF
  chmod 644 "$DESKTOP/Active-Alpha-Chat.desktop"
  echo "[OK] Terminal: active-alpha-chat"
  echo "[OK] Desktop: $DESKTOP/Active-Alpha-Chat.desktop"
}

export AA_PROJECT_ROOT="$ROOT"
install_ollama
start_ollama
pull_model
write_launchers
"$PY" tools/active_alpha_chat.py --health
"$PY" -c "
from pathlib import Path
from analytics.operator_public_status import publish_public_status
publish_public_status(Path('$ROOT'), notify=False)
print('[OK] Public status aktualisiert')
"
echo "[OK] Stufe 3 bereit — active-alpha-chat"
