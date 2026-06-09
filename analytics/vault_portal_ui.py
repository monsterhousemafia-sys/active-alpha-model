"""Schlüssel-Tresor UI — Apple-inspiriert: klar, ruhig, privatsphäre-zentriert."""
from __future__ import annotations

import html
from typing import Optional


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _step_item(num: int, title: str, desc: str, *, active: bool, done: bool) -> str:
    cls = "step-item"
    if active:
        cls += " active"
    if done:
        cls += " done"
    mark = "✓" if done else str(num)
    return f"""
    <div class="{cls}">
      <div class="step-badge">{_esc(mark)}</div>
      <div class="step-copy">
        <div class="step-title">{_esc(title)}</div>
        <div class="step-desc">{_esc(desc)}</div>
      </div>
    </div>"""


def render_vault_page(
    *,
    session: str,
    ok: Optional[bool] = None,
    msg: str = "",
    mode: str = "setup",
    reason_de: str = "",
    cloudflare_login_url: str = "",
    existing_url: str = "",
    active_step: int = 1,
    form_action: str = "/local/vault/store",
) -> bytes:
    titles = {
        "setup": ("Schlüssel einrichten", "Einmalig. Sicher. Nur auf diesem Gerät."),
        "manage": ("Schlüssel verwalten", "Änderungen bleiben auf diesem Gerät."),
        "migrate": ("Schlüssel überführen", "Aus Klartext in verschlüsselten Tresor."),
    }
    headline, subtitle = titles.get(mode, ("Schlüssel-Tresor", "Privatsphäre zuerst."))

    banner = ""
    if ok is True:
        banner = (
            f'<div class="banner ok" role="status">'
            f'<span class="dot"></span>{_esc(msg or "Gespeichert. Du kannst dieses Fenster schließen.")}'
            f"</div>"
        )
    elif ok is False:
        banner = (
            f'<div class="banner err" role="alert">'
            f'<span class="dot"></span>{_esc(msg or "Eingabe konnte nicht gespeichert werden.")}'
            f"</div>"
        )

    reason = f'<p class="reason">{_esc(reason_de)}</p>' if reason_de else ""

    step = max(1, min(int(active_step or 1), 3))
    has_cf = bool(cloudflare_login_url)
    steps_html = "".join(
        [
            _step_item(
                1,
                "Bei Cloudflare anmelden",
                "Passwort nur auf der Anmeldeseite — nie im Chat.",
                active=step == 1 and has_cf,
                done=step > 1 or (not has_cf and step >= 2),
            ),
            _step_item(
                2,
                "Tresor-Passphrase festlegen",
                "Mindestens 12 Zeichen — nur auf diesem Gerät.",
                active=step == 2,
                done=step > 2,
            ),
            _step_item(
                3,
                "Tunnel aktivieren",
                "Automatisch nach „Sichern“ — Hub + Remote-URL.",
                active=step == 3,
                done=ok is True,
            ),
        ]
    )

    cf_link = ""
    if cloudflare_login_url:
        cf_link = (
            f'<a class="link-btn" href="{_esc(cloudflare_login_url)}" target="_blank" rel="noopener">'
            f"Cloudflare öffnen</a>"
        )

    token_ph = "Unverändert lassen" if mode == "manage" else "eyJ… (nach Anmeldung)"
    submit = "Sichern" if mode != "manage" else "Änderungen sichern"
    show_form = ok is not True

    form_block = ""
    if show_form:
        form_block = f"""
    <form method="post" action="{_esc(form_action)}" autocomplete="off" id="vault-form">
      <input type="hidden" name="session" value="{_esc(session)}">
      <section class="field-group" data-step="2">
        <div class="group-label">Tresor-Passphrase</div>
        <label for="vault_passphrase">Passphrase (min. 12 Zeichen)</label>
        <div class="pw-wrap">
          <input id="vault_passphrase" type="password" name="vault_passphrase"
                 autocomplete="new-password" spellcheck="false"
                 placeholder="Nur auf diesem Gerät — nie im Chat" minlength="12">
          <button type="button" class="pw-toggle" data-target="vault_passphrase" aria-label="Passphrase anzeigen">Anzeigen</button>
        </div>
        <div class="strength" id="strength" aria-live="polite">
          <div class="strength-bar"><span id="strength-fill"></span></div>
          <span class="strength-label" id="strength-label">Passphrase eingeben</span>
        </div>
      </section>
      <section class="field-group" data-step="2">
        <div class="group-label">Cloudflare-Tunnel</div>
        <label for="tunnel_token">Tunnel-Token</label>
        <div class="pw-wrap">
          <input id="tunnel_token" type="password" name="tunnel_token"
                 autocomplete="new-password" spellcheck="false" placeholder="{_esc(token_ph)}">
          <button type="button" class="pw-toggle" data-target="tunnel_token" aria-label="Token anzeigen">Anzeigen</button>
        </div>
        <label class="check">
          <input type="checkbox" name="auto_provision" value="1" checked>
          Token automatisch von Cloudflare laden (nach Schritt 1)
        </label>
        <label for="tunnel_url">Öffentliche URL</label>
        <input id="tunnel_url" type="url" name="tunnel_url" value="{_esc(existing_url)}"
               placeholder="https://…" autocomplete="off">
      </section>
      <button type="submit" class="primary">{_esc(submit)}</button>
    </form>"""

    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Active Alpha — Schlüssel</title>
<style>
:root {{
  --bg: #f5f5f7;
  --card: rgba(255,255,255,0.82);
  --text: #1d1d1f;
  --muted: #6e6e73;
  --line: rgba(0,0,0,0.08);
  --accent: #0071e3;
  --accent-h: #0077ed;
  --ok: #1d7a3a;
  --err: #d70015;
  --shadow: 0 18px 50px rgba(0,0,0,0.08);
  --radius: 18px;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #000;
    --card: rgba(28,28,30,0.84);
    --text: #f5f5f7;
    --muted: #a1a1a6;
    --line: rgba(255,255,255,0.12);
    --shadow: 0 18px 50px rgba(0,0,0,0.45);
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  min-height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  background: radial-gradient(ellipse at top, #ffffff 0%, var(--bg) 55%);
  color: var(--text);
  -webkit-font-smoothing: antialiased;
}}
@media (prefers-color-scheme: dark) {{
  body {{ background: radial-gradient(ellipse at top, #1c1c1e 0%, #000 60%); }}
}}
.wrap {{
  max-width: 460px;
  margin: 0 auto;
  padding: 44px 22px 32px;
}}
.hero {{ text-align: center; margin-bottom: 24px; }}
.lock {{
  width: 56px; height: 56px; margin: 0 auto 16px;
  border-radius: 16px;
  background: linear-gradient(145deg, #34c759, #30b0c7);
  display: grid; place-items: center;
  box-shadow: 0 8px 24px rgba(52,199,89,0.35);
}}
.lock svg {{ width: 28px; height: 28px; fill: #fff; }}
.eyebrow {{
  font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 8px;
}}
h1 {{
  font-size: 28px; font-weight: 600; letter-spacing: -0.02em;
  margin: 0 0 8px; line-height: 1.15;
}}
.lead {{ font-size: 15px; color: var(--muted); margin: 0; line-height: 1.45; }}
.card {{
  backdrop-filter: saturate(180%) blur(20px);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 22px;
}}
.privacy {{
  display: flex; gap: 10px; align-items: flex-start;
  font-size: 13px; color: var(--muted); line-height: 1.45;
  margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--line);
}}
.privacy svg {{ flex-shrink: 0; margin-top: 2px; }}
.reason {{ font-size: 14px; color: var(--text); margin: 0 0 14px; }}
.banner {{
  display: flex; align-items: center; gap: 8px;
  font-size: 14px; padding: 10px 12px; border-radius: 12px; margin-bottom: 14px;
}}
.banner.ok {{ background: rgba(52,199,89,0.12); color: var(--ok); }}
.banner.err {{ background: rgba(255,59,48,0.12); color: var(--err); }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; background: currentColor; flex-shrink: 0; }}
.steps {{
  display: flex; flex-direction: column; gap: 8px;
  margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid var(--line);
}}
.step-item {{
  display: flex; gap: 12px; align-items: flex-start;
  padding: 10px 12px; border-radius: 14px;
  background: rgba(127,127,127,0.05);
  transition: background 0.2s;
}}
.step-item.active {{
  background: rgba(0,113,227,0.08);
  outline: 1px solid rgba(0,113,227,0.25);
}}
.step-item.done .step-badge {{
  background: var(--ok);
}}
.step-badge {{
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--muted); color: #fff; font-size: 13px; font-weight: 600;
  display: grid; place-items: center; flex-shrink: 0;
}}
.step-item.active .step-badge {{ background: var(--accent); }}
.step-title {{ font-size: 14px; font-weight: 600; }}
.step-desc {{ font-size: 12px; color: var(--muted); margin-top: 2px; line-height: 1.4; }}
.link-btn {{
  display: inline-block; margin-top: 10px; padding: 8px 14px;
  font-size: 13px; font-weight: 600; color: #fff; text-decoration: none;
  background: var(--accent); border-radius: 980px;
}}
.link-btn:hover {{ background: var(--accent-h); }}
.field-group {{ margin-bottom: 16px; }}
.group-label {{
  font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 10px;
}}
label {{
  display: block; font-size: 12px; color: var(--muted); margin: 10px 0 6px;
}}
input[type="url"], input[type="password"], input[type="text"] {{
  width: 100%; padding: 12px 14px; font-size: 15px;
  border-radius: 12px; border: 1px solid var(--line);
  background: rgba(127,127,127,0.06); color: var(--text);
  outline: none;
}}
input:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgba(0,113,227,0.2); }}
.pw-wrap {{ position: relative; }}
.pw-wrap input {{ padding-right: 88px; }}
.pw-toggle {{
  position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
  border: 0; background: transparent; color: var(--accent);
  font-size: 12px; font-weight: 600; cursor: pointer; padding: 6px 8px;
}}
.strength {{ margin-top: 8px; }}
.strength-bar {{
  height: 4px; border-radius: 4px; background: rgba(127,127,127,0.2); overflow: hidden;
}}
.strength-bar span {{
  display: block; height: 100%; width: 0%;
  background: var(--err); transition: width 0.2s, background 0.2s;
}}
.strength-label {{ font-size: 11px; color: var(--muted); margin-top: 4px; display: block; }}
button.primary {{
  width: 100%; margin-top: 8px; padding: 13px 16px;
  border: 0; border-radius: 980px;
  background: var(--accent); color: #fff;
  font-size: 15px; font-weight: 600; cursor: pointer;
}}
button.primary:hover {{ background: var(--accent-h); }}
.check {{ display:flex; align-items:flex-start; gap:8px; font-size:13px; color:var(--muted); margin-top:10px; }}
.check input {{ margin-top:3px; width:auto; }}
.foot {{
  text-align: center; margin-top: 22px;
  font-size: 11px; color: var(--muted); line-height: 1.5;
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="lock" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M12 1a5 5 0 00-5 5v3H6a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V11a2 2 0 00-2-2h-1V6a5 5 0 00-5-5zm-3 8V6a3 3 0 016 0v3H9z"/></svg>
    </div>
    <div class="eyebrow">Privatsphäre</div>
    <h1>{_esc(headline)}</h1>
    <p class="lead">{_esc(subtitle)}</p>
  </div>
  <div class="card">
    <div class="privacy">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      <span>Luftspalt aktiv: nur 127.0.0.1, doppelt verschlüsselt (Gerät + Passphrase), kein Internet-Zugriff auf den Tresor.</span>
    </div>
    {reason}{banner}
    <div class="steps" aria-label="Fortschritt">{steps_html}</div>
    {cf_link}
    {form_block}
  </div>
  <p class="foot">Nur dieses Gerät · 127.0.0.1 · Sitzung 15 Min.<br>Active Alpha Schlüssel-Tresor</p>
</div>
<script>
(function() {{
  document.querySelectorAll('.pw-toggle').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      var id = btn.getAttribute('data-target');
      var el = document.getElementById(id);
      if (!el) return;
      var show = el.type === 'password';
      el.type = show ? 'text' : 'password';
      btn.textContent = show ? 'Verbergen' : 'Anzeigen';
    }});
  }});
  var pp = document.getElementById('vault_passphrase');
  var fill = document.getElementById('strength-fill');
  var label = document.getElementById('strength-label');
  if (pp && fill && label) {{
    pp.addEventListener('input', function() {{
      var v = pp.value || '';
      var score = 0;
      if (v.length >= 8) score++;
      if (v.length >= 12) score++;
      if (/[A-Z]/.test(v) && /[a-z]/.test(v)) score++;
      if (/[0-9]/.test(v)) score++;
      if (/[^A-Za-z0-9]/.test(v)) score++;
      var pct = Math.min(100, score * 20);
      fill.style.width = pct + '%';
      var colors = ['#d70015', '#ff9500', '#ffcc00', '#34c759', '#30b0c7'];
      var texts = ['Zu kurz', 'Schwach', 'Mittel', 'Gut', 'Sehr gut'];
      var idx = Math.max(0, Math.min(score - 1, 4));
      if (!v) {{ fill.style.width = '0%'; label.textContent = 'Passphrase eingeben'; return; }}
      fill.style.background = colors[idx];
      label.textContent = texts[idx] + (v.length < 12 ? ' — min. 12 Zeichen' : '');
    }});
  }}
}})();
</script>
</body>
</html>"""
    return page.encode("utf-8")
