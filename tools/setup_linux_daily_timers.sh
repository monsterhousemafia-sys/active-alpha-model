#!/usr/bin/env bash
# systemd user timers — learn, warnings, headless refresh, trading-day orchestrator.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PY="${ROOT}/.venv/bin/python3"
mkdir -p "$UNIT_DIR"

write_unit() {
  local name="$1"
  local schedule="$2"
  local cmd="$3"
  cat >"$UNIT_DIR/active-alpha-${name}.service" <<EOF
[Unit]
Description=Active Alpha — ${name}
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${ROOT}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT=${ROOT}
ExecStart=${cmd}
EOF
  cat >"$UNIT_DIR/active-alpha-${name}.timer" <<EOF
[Unit]
Description=Active Alpha timer — ${name}

[Timer]
OnCalendar=${schedule}
Persistent=true

[Install]
WantedBy=timers.target
EOF
}

write_unit_multi() {
  local name="$1"
  local cmd="$2"
  shift 2
  cat >"$UNIT_DIR/active-alpha-${name}.service" <<EOF
[Unit]
Description=Active Alpha — ${name}
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${ROOT}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT=${ROOT}
ExecStart=${cmd}
EOF
  {
    echo "[Unit]"
    echo "Description=Active Alpha timer — ${name}"
    echo ""
    echo "[Timer]"
    for sched in "$@"; do
      echo "OnCalendar=${sched}"
    done
    echo "Persistent=true"
    echo ""
    echo "[Install]"
    echo "WantedBy=timers.target"
  } >"$UNIT_DIR/active-alpha-${name}.timer"
}

write_unit "prognosis-eod" "*-*-* 22:15:00" "bash ${ROOT}/tools/king_ops.sh prognosis run"
write_unit_multi "t212-watch" \
  "bash ${ROOT}/tools/king_ops.sh t212-watch" \
  "*-*-* *:00/10:00"
write_unit_multi "r3-quotes" \
  "bash ${ROOT}/tools/king_ops.sh r3-quotes" \
  "*-*-* *:00/5:00"
write_unit_multi "r3-aktuell" \
  "bash ${ROOT}/tools/king_ops.sh r3-aktuell" \
  "Mon..Fri *-*-* *:00/15:00"
write_unit_multi "daily-alpha-preus" \
  "bash ${ROOT}/tools/king_ops.sh daily-alpha pre-us" \
  "Mon..Fri *-*-* 15:10:00" \
  "Mon..Fri *-*-* 15:20:00"
write_unit "daily-alpha-eod" "Mon..Fri *-*-* 22:10:00" "bash ${ROOT}/tools/king_ops.sh daily-alpha eod"
write_unit_multi "alpha-engine" \
  "bash ${ROOT}/tools/king_ops.sh alpha-engine" \
  "*-*-* *:00/30:00"
write_unit_multi "stufe-a" \
  "bash ${ROOT}/tools/king_ops.sh stufe-a" \
  "Mon..Fri *-*-* *:00/45:00"
write_unit "learn" "*-*-* 22:05:00" "${PY} ${ROOT}/tools/ai_kernel.py learn"
write_unit "gui-preview" "*-*-* 22:25:00" "${PY} ${ROOT}/tools/ai_kernel.py gui-preview"
write_unit "warnings" "Mon..Fri *-*-* 14:25:00" "${PY} ${ROOT}/tools/ai_kernel.py warnings"
write_unit "h1-watch" "*-*-* 08,12,16,20:00:00" "${PY} ${ROOT}/tools/ai_kernel.py h1-watch"
write_unit "trading-day" "Mon..Fri *-*-* 14:00:00" "${PY} ${ROOT}/tools/ai_kernel.py trading-day --trading-day-phase full"

REFRESH_SCHEDULES=()
for hour in 14 15 16 17 18 19 20 21 22; do
  if [[ "${hour}" -eq 14 ]]; then
    REFRESH_SCHEDULES+=("Mon..Fri *-*-* 14:30:00")
  else
    REFRESH_SCHEDULES+=("Mon..Fri *-*-* ${hour}:00:00")
  fi
  if [[ "${hour}" -lt 22 ]]; then
    REFRESH_SCHEDULES+=("Mon..Fri *-*-* ${hour}:30:00")
  fi
done
write_unit_multi "refresh" \
  "${PY} ${ROOT}/tools/ai_kernel.py refresh --refresh-mode snapshot" \
  "${REFRESH_SCHEDULES[@]}"

PREUS_SCHEDULES=(
  "Mon..Fri *-*-* 15:15:00"
  "Mon..Fri *-*-* 15:25:00"
)
write_unit_multi "refresh-preus" \
  "${PY} ${ROOT}/tools/ai_kernel.py trading-day --trading-day-phase pre-us" \
  "${PREUS_SCHEDULES[@]}"

USOPEN_SCHEDULES=()
for minute in 30 35 40 45 50 55; do
  USOPEN_SCHEDULES+=("Mon..Fri *-*-* 15:${minute}:00")
done
for minute in 00 05 10 15 20 25 30; do
  USOPEN_SCHEDULES+=("Mon..Fri *-*-* 16:${minute}:00")
done
write_unit_multi "refresh-usopen" \
  "${PY} ${ROOT}/tools/ai_kernel.py trading-day --trading-day-phase us-open" \
  "${USOPEN_SCHEDULES[@]}"

# Legacy timers ersetzt durch trading-day
for legacy in monday-prep refresh-daily; do
  systemctl --user disable "active-alpha-${legacy}.timer" 2>/dev/null || true
  rm -f "$UNIT_DIR/active-alpha-${legacy}.timer" "$UNIT_DIR/active-alpha-${legacy}.service"
done

systemctl --user daemon-reload
for t in prognosis-eod t212-watch r3-quotes r3-aktuell daily-alpha-preus daily-alpha-eod alpha-engine stufe-a gui-preview learn warnings h1-watch trading-day refresh refresh-preus refresh-usopen; do
  systemctl --user enable --now "active-alpha-${t}.timer"
done

echo "[OK] Timer: active-alpha-trading-day.timer (Mo–Fr 14:00 — Orchestrator)"
echo "[OK] Timer: active-alpha-refresh.timer (Mo–Fr 14:30–22:00 alle 30 min, dedup)"
echo "[OK] Timer: active-alpha-refresh-preus.timer (Mo–Fr 15:15 + 15:25)"
echo "[OK] Timer: active-alpha-refresh-usopen.timer (Mo–Fr 15:30–16:30 alle 5 min)"
echo "[OK] Timer: active-alpha-prognosis-eod.timer (täglich 22:15 — Prognose-Freischaltung)"
echo "[OK] Timer: active-alpha-t212-watch.timer (alle 10 min — 24/7 T212+Prognose)"
echo "[OK] Timer: active-alpha-r3-quotes.timer (alle 5 min — Kurse/Ingest coalesced)"
echo "[OK] Timer: active-alpha-r3-aktuell.timer (Mo–Fr alle 15 min — Hub+GUI+Mirror+Daten)"
echo "[OK] Timer: active-alpha-daily-alpha-preus.timer (Mo–Fr 15:10+15:20 — Top-Picks vor US-Open)"
echo "[OK] Timer: active-alpha-daily-alpha-eod.timer (Mo–Fr 22:10 — EOD-Signal+Postmortem+Learning)"
echo "[OK] Timer: active-alpha-alpha-engine.timer (alle 30 min — Hintergrund-Engine)"
echo "[OK] Timer: active-alpha-stufe-a.timer (Mo–Fr alle 45 min — König Stufe A)"
echo "[OK] Timer: active-alpha-learn.timer (22:05 — Worker für Preview)"
echo "[OK] Timer: active-alpha-gui-preview.timer (22:25 — Tages-Aggregator / König)"
echo "[OK] Timer: active-alpha-warnings.timer (Mo–Fr 14:25, cached snap)"
echo "[OK] Timer: active-alpha-h1-watch.timer (4× täglich)"
systemctl --user list-timers 'active-alpha-*' --no-pager
