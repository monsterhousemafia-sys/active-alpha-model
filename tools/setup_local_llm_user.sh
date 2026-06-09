#!/usr/bin/env bash
# Stufe 3 — Ollama user-local (ohne sudo/curl).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
MODEL="${AA_LOCAL_LLM_MODEL:-qwen2.5:7b}"
OLLAMA_DIR="${HOME}/.local/share/ollama"
BIN_DIR="${HOME}/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
VER="${OLLAMA_VERSION:-v0.30.6}"
ARCH="amd64"
mkdir -p "$OLLAMA_DIR" "$BIN_DIR" "$UNIT_DIR"

if [[ ! -x "$OLLAMA_DIR/bin/ollama" ]]; then
  echo "[D] Lade Ollama ${VER} (~1.3 GB) …"
  command -v wget >/dev/null || { echo "[FEHLER] wget fehlt" >&2; exit 1; }
  command -v zstd >/dev/null || { echo "[FEHLER] zstd fehlt — sudo apt install zstd" >&2; exit 1; }
  wget --progress=dot:giga -O - \
    "https://github.com/ollama/ollama/releases/download/${VER}/ollama-linux-${ARCH}.tar.zst" \
    | zstd -d | tar -xf - -C "$OLLAMA_DIR"
fi

ln -sf "$OLLAMA_DIR/bin/ollama" "$BIN_DIR/ollama"
export PATH="$BIN_DIR:$PATH"

cat >"$UNIT_DIR/ollama.service" <<EOF
[Unit]
Description=Ollama local LLM (user)
After=network-online.target

[Service]
ExecStart=${OLLAMA_DIR}/bin/ollama serve
Restart=on-failure
Environment=HOME=${HOME}
Environment=PATH=${BIN_DIR}:/usr/bin:/bin
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_KEEP_ALIVE=5m
Environment=OLLAMA_NUM_THREADS=8

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now ollama.service 2>/dev/null || {
  pgrep -x ollama >/dev/null || nohup "$OLLAMA_DIR/bin/ollama" serve >/tmp/ollama-serve.log 2>&1 &
  sleep 3
}

echo "[INFO] Modell $MODEL …"
ollama pull "$MODEL"

bash "$ROOT/tools/setup_local_llm.sh" 2>/dev/null || {
  chmod +x "$ROOT/tools/active_alpha_chat.py"
  ln -sf "$ROOT/tools/active_alpha_chat.py" "$BIN_DIR/active-alpha-chat"
}

export AA_PROJECT_ROOT="$ROOT"
"$PY" tools/ai_kernel.py llm-health
echo "[OK] Stufe 3 user-local — active-alpha-chat"
