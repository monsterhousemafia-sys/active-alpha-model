"""R3 — T212 Zugangsdaten-Formular im Exec-Spiegel (/r3). Domain: r3_t212_operator_api."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from analytics.r3_t212_operator_api import (
    OPERATOR_SETUP_REL,
    credentials_configured,
    load_operator_setup,
    mark_operator_api_setup_complete,
    needs_operator_api_setup,
    operator_api_ready,
    resolve_operator_api_state,
    save_t212_credentials_from_web,
)

__all__ = [
    "OPERATOR_SETUP_REL",
    "credentials_configured",
    "load_operator_setup",
    "mark_operator_api_setup_complete",
    "needs_operator_api_setup",
    "operator_api_ready",
    "resolve_operator_api_state",
    "save_t212_credentials_from_web",
    "render_t212_setup_panel",
    "t212_setup_css",
    "t212_setup_js",
]


def render_t212_setup_panel(root: Path, *, show: bool) -> str:
    del root
    if not show:
        return ""
    return """
<section class="r3-t212-setup" id="r3-t212-setup" aria-label="T212 API">
  <h2 class="r3-t212-setup-title">T212 API</h2>
  <label class="r3-t212-setup-field">
    <span>Key</span>
    <input type="password" id="r3-t212-key" autocomplete="off" placeholder="Key" />
  </label>
  <label class="r3-t212-setup-field">
    <span>Secret</span>
    <input type="password" id="r3-t212-secret" autocomplete="off" placeholder="Secret" />
  </label>
  <button type="button" class="r3-t212-setup-btn" id="r3-t212-save-btn" onclick="r3SaveT212Credentials()">
    Speichern
  </button>
  <p class="r3-t212-setup-hint" id="r3-t212-setup-msg"></p>
</section>
"""


def t212_setup_css() -> str:
    return """
.r3-t212-setup {
  padding: var(--r3-pad-lg); background: var(--r3-bg);
  border: 1px solid var(--r3-border); border-radius: var(--r3-radius);
}
.r3-t212-setup-title { margin: 0 0 var(--r3-gap); font-size: 16px; font-weight: 700; }
.r3-t212-setup-field { display: block; margin: 0 0 var(--r3-gap); }
.r3-t212-setup-field span { display: block; font-size: 11px; font-weight: 600; color: var(--r3-muted); margin-bottom: 4px; }
.r3-t212-setup-field input {
  width: 100%; box-sizing: border-box; padding: 10px 12px;
  border: 1px solid var(--r3-border); border-radius: var(--r3-radius-sm);
  background: var(--r3-surface); color: inherit; font-size: 14px;
}
.r3-t212-setup-btn {
  width: 100%; padding: var(--r3-pad); margin-top: var(--r3-gap);
  border: none; border-radius: var(--r3-radius); font-weight: 700; font-size: 14px;
  background: linear-gradient(145deg, var(--r3-orange-top), var(--r3-orange-bottom));
  color: #fff; cursor: pointer;
}
.r3-t212-setup-hint { margin: var(--r3-gap) 0 0; font-size: 12px; color: var(--r3-muted); min-height: 1.2em; }
"""


def t212_setup_js() -> str:
    return """
async function r3SaveT212Credentials() {
  const keyEl = document.getElementById('r3-t212-key');
  const secEl = document.getElementById('r3-t212-secret');
  const msg = document.getElementById('r3-t212-setup-msg');
  const btn = document.getElementById('r3-t212-save-btn');
  const key = keyEl ? keyEl.value.trim() : '';
  const secret = secEl ? secEl.value.trim() : '';
  if (!key || !secret) {
    if (msg) msg.textContent = 'API eingeben';
    return;
  }
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    const r = await fetch('/api/r3/t212/credentials', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key, api_secret: secret }),
      cache: 'no-store',
    });
    const j = await r.json();
    if (msg) msg.textContent = j.message_de || (j.ok ? 'Gespeichert' : 'API eingeben');
    if (j.ok) {
      if (keyEl) keyEl.value = '';
      if (secEl) secEl.value = '';
      setTimeout(() => { r3RefreshUiPreferSoft(); }, 400);
      return;
    }
  } catch (e) {
    if (msg) msg.textContent = 'Erneut versuchen';
  }
  if (btn) { btn.disabled = false; btn.textContent = 'Speichern'; }
}
"""
