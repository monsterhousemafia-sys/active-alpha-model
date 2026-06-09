#!/usr/bin/env bash
# Marktanalyse — Bash-Cockpit (ehemalige EXE-Logik, headless, fail-closed).
# Usage: bash tools/marktanalyse_bash.sh <command>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tools/marktanalyse_common.sh
source "$ROOT/tools/marktanalyse_common.sh"

CMD="${1:-start}"
shift || true

_ma_king_status() {
  bash "$ROOT/tools/king_status.sh"
}

_ma_predict() {
  bash "$ROOT/tools/linux_live_ops.sh" predict "$@"
}

_ma_network() {
  bash "$ROOT/tools/king_ops.sh" network
}

_ma_start() {
  ma_banner "START"
  ma_section "Preflight"
  if ma_view preflight; then
    echo "[OK] Preflight"
  else
    echo "[BLOCK] Preflight — Details oben"
  fi
  echo ""
  ma_section "Status"
  ma_view status || true
  echo ""
  ma_section "Top-Picks"
  ma_view picks || true
  echo ""
  _ma_king_status
  ma_write_evidence
  echo ""
  echo "Weiter: bash tools/marktanalyse_bash.sh menu | predict | cockpit"
}

_ma_menu() {
  ma_banner "MENÜ"
  while true; do
    cat <<'MENU'

  1) Status       5) Gates        9) Netzwerk
  2) Picks        6) Preflight   c) GPT-4o (Bash)
  3) Predict      7) Cockpit     k) König (agent)
  4) Start        8) king status  g) GUI (Desktop)
                                  q) Beenden
MENU
    printf "Auswahl: "
    read -r choice || choice=q
    case "$choice" in
      1) ma_view status || true ;;
      2) ma_view picks ;;
      3) _ma_predict ;;
      4) _ma_start ;;
      5) ma_view gates ;;
      6) ma_view preflight || true ;;
      7) ma_view cockpit ;;
      8) _ma_king_status ;;
      9) _ma_network ;;
      c|C) bash "$ROOT/tools/bash_gpt4o.sh" menu ;;
      k|K) exec bash "$ROOT/tools/king_ops.sh" agent ;;
      g|G)
        if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
          exec bash "$ROOT/run_marktanalyse_linux.sh" --dev
        else
          echo "[FEHLER] Kein Display — nur Bash-Cockpit verfügbar." >&2
        fi
        ;;
      q|Q) echo "Beendet."; ma_write_evidence; exit 0 ;;
      *) echo "Unbekannt: $choice" ;;
    esac
    echo ""
  done
}

case "$CMD" in
  start|run)
    _ma_start
    ;;
  preflight|check)
    ma_view preflight "$@"
    ;;
  status|st)
    ma_banner "STATUS"
    ma_view status "$@"
    ma_write_evidence
    ;;
  picks|signal|top)
    ma_view picks "$@"
    ;;
  cockpit|cockpit-de|decision)
    ma_view cockpit "$@"
    ;;
  gates|blockers|gate)
    ma_view gates "$@"
    ;;
  predict|eod)
    _ma_predict "$@"
    ma_write_evidence
    ;;
  king|h1)
    _ma_king_status
    ;;
  network|takt)
    _ma_network
    ;;
  gpt|gpt4o|chat)
    exec bash "$ROOT/tools/bash_gpt4o.sh" "${1:-menu}" "${@:2}"
    ;;
  ask)
    exec bash "$ROOT/tools/bash_gpt4o.sh" ask "$@"
    ;;
  menu|interactive|i)
    _ma_menu
    ;;
  gui|desktop)
    if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
      exec bash "$ROOT/run_marktanalyse_linux.sh" "$@"
    fi
    echo "[FEHLER] Kein Grafik-Display — nutze: bash tools/marktanalyse_bash.sh start" >&2
    exit 1
    ;;
  json|bundle)
    ma_view bundle --json "$@"
    ;;
  help|-h|--help|*)
    cat <<'EOF'
marktanalyse_bash.sh — Marktanalyse als Bash-Cockpit (ohne EXE/GUI)

  start               Preflight + Status + Picks + König-Status
  status              Kurzstatus + Evidence schreiben
  preflight           Champion-Guard + Minimal-Flow
  picks               Top-Picks aus prediction_readiness
  cockpit             Decision-Cockpit (read-only Snapshot)
  gates               Alle operativen Blocker
  predict             Tages-Signal (linux_live_ops, compute-only)
  king                king_status.sh
  network             Netzwerk-Takt synchronisieren
  gpt|chat            GPT-4o Berater (ein Modell — Bash)
  menu                Interaktives Menü
  gui                 PySide6-UI (nur mit DISPLAY)
  json                Status-Bundle als JSON

Beispiele:
  bash tools/marktanalyse_bash.sh start
  bash run_marktanalyse_bash.sh menu
  bash tools/king_ops.sh marktanalyse status

Safety: AA_EXECUTION_DRY_RUN=1 · keine Orders von Linux.
EOF
    ;;
esac
