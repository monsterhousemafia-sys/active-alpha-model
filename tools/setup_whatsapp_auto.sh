#!/usr/bin/env bash
# Auto-Send ohne Docker — Playwright (voll) oder xdotool (Text+Enter).
set -euo pipefail
_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tools/r3_common.sh
source "$_ROOT/tools/r3_common.sh"
r3_init

CMD="${1:-check}"
shift || true

case "$CMD" in
  auth|qr|login)
    echo "[auto] Playwright-Session — QR einmal scannen …"
    "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_auto_send import _session_dir, playwright_available
from analytics.whatsapp_spread import load_whatsapp_config
r = Path('$_ROOT')
if not playwright_available():
    raise SystemExit('pip install playwright && playwright install chromium')
cfg = load_whatsapp_config(r)
session = _session_dir(r, cfg)
session.mkdir(parents=True, exist_ok=True)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(session), headless=False)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://web.whatsapp.com/', wait_until='domcontentloaded', timeout=120000)
    print('[auto] WhatsApp Web offen — QR scannen, dann Enter hier …')
    input()
    ctx.close()
print('[OK] Session:', session)
"
    ;;
  install|deps)
    echo "[auto] Optionale Abhängigkeiten …"
    "$R3_PY" -m pip install playwright pyautogui python-xlib -q
    if command -v firefox >/dev/null 2>&1; then
      echo "[OK] Firefox vorhanden — Playwright-Browser optional (Ubuntu 26: nur Firefox)"
    else
      "$R3_PY" -m playwright install chromium 2>/dev/null || echo "[WARN] Playwright-Browser — siehe Firefox"
    fi
    bash "$_ROOT/tools/setup_whatsapp_auto.sh" profile
    for pkg in xclip xdotool wl-copy xsel; do
      if command -v "$pkg" >/dev/null 2>&1; then
        echo "[OK] $pkg installiert"
      else
        echo "[FEHLT] $pkg — optional; Auto-Send: python-xlib. Clipboard/ZIP: sudo apt install -y xclip xdotool wl-clipboard xsel"
      fi
    done
    ;;
  profile|firefox-profile|datenschutz)
    "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_auto_send import bootstrap_firefox_profile, firefox_profile_dir
from analytics.whatsapp_spread import load_whatsapp_config
import json
r = Path('$_ROOT')
cfg = load_whatsapp_config(r)
doc = bootstrap_firefox_profile(firefox_profile_dir(r, cfg))
print(json.dumps(doc, ensure_ascii=False, indent=2))
"
    ;;
  check|status|*)
    "$R3_PY" -c "
from pathlib import Path
from analytics.whatsapp_auto_send import auto_send_capabilities, bootstrap_firefox_profile, firefox_profile_dir
from analytics.whatsapp_spread import load_whatsapp_config
import json
r = Path('$_ROOT')
cfg = load_whatsapp_config(r)
bootstrap_firefox_profile(firefox_profile_dir(r, cfg))
print(json.dumps({'auto_send_mode': cfg.get('auto_send_mode'), 'capabilities': auto_send_capabilities(r, cfg)}, ensure_ascii=False, indent=2))
"
    ;;
esac
