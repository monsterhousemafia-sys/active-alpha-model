"""R3 Login-Screen — Phase B Meilenstein 1."""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any, Dict

from analytics.r3_session_manager import (
    end_session,
    load_login_config,
    mark_session_started,
    session_status_doc,
)


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def build_login_context(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_login_config(root)
    user = os.environ.get("USER") or "operator"
    hostname = os.uname().nodename
    sess = session_status_doc(root)
    logind = sess.get("logind") or {}
    return {
        "title_de": cfg.get("title_de"),
        "subtitle_de": cfg.get("subtitle_de"),
        "user": user,
        "hostname": hostname,
        "brand_mark": cfg.get("brand_mark") or "R3",
        "brand_color": cfg.get("brand_color") or "#E95420",
        "post_login_path": cfg.get("post_login_path") or "/desktop",
        "session_active": bool(sess.get("r3_session_active")),
        "session_headline": logind.get("headline_de") or sess.get("headline_de"),
        "graphical": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    }


def render_login_page(root: Path, *, port: int = 17890) -> bytes:
    root = Path(root)
    ctx = build_login_context(root)
    active = ctx.get("session_active")
    post = _esc(ctx.get("post_login_path"))
    user = _esc(ctx.get("user"))
    host = _esc(ctx.get("hostname"))
    headline = _esc(ctx.get("session_headline"))
    mark = _esc(ctx.get("brand_mark"))
    color = _esc(ctx.get("brand_color"))
    title = _esc(ctx.get("title_de"))
    sub = _esc(ctx.get("subtitle_de"))

    cta = (
        f'<a class="r3-login-go" href="{post}">Weiter zu R3 Desktop</a>'
        if active
        else '<button type="button" class="r3-login-go" id="r3-login-start">R3 Sitzung starten</button>'
    )
    hint = (
        "Sitzung aktiv — Desktop öffnen."
        if active
        else "Linux-Unterbau bleibt — R3 ist deine sichtbare Sitzung."
    )

    html_out = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title} — Login</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; min-height: 100vh; display: grid; place-items: center;
      font-family: system-ui, -apple-system, sans-serif;
      background: radial-gradient(ellipse at 30% 20%, #1a1a22, #0a0a0f 70%);
      color: #f2f2f7;
    }}
    .card {{
      width: min(420px, 92vw); padding: 36px 32px 32px; border-radius: 24px;
      background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);
      box-shadow: 0 24px 64px rgba(0,0,0,.45); text-align: center;
    }}
    .mark {{
      width: 72px; height: 72px; border-radius: 18px; margin: 0 auto 20px;
      background: {color}; display: grid; place-items: center;
      font-weight: 800; font-size: 22px; color: #fff;
    }}
    h1 {{ margin: 0 0 8px; font-size: 22px; font-weight: 600; }}
    .sub {{ margin: 0 0 20px; color: #a1a1a6; font-size: 14px; }}
    .pill {{
      display: inline-flex; gap: 8px; flex-wrap: wrap; justify-content: center;
      margin-bottom: 24px;
    }}
    .pill span {{
      font-size: 12px; padding: 7px 12px; border-radius: 999px;
      background: rgba(255,255,255,.08); color: #d1d1d6;
    }}
    .r3-login-go {{
      display: inline-block; width: 100%; padding: 14px 18px; border: 0; border-radius: 14px;
      background: {color}; color: #fff; font: inherit; font-size: 15px; font-weight: 600;
      cursor: pointer; text-decoration: none;
    }}
    .r3-login-go:hover {{ filter: brightness(1.06); }}
    .r3-login-go:disabled {{ opacity: .6; cursor: wait; }}
    .hint {{ margin-top: 16px; font-size: 12px; color: #8e8e93; line-height: 1.45; }}
    .err {{ color: #ff6b6b; font-size: 13px; margin-top: 12px; min-height: 1.2em; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="mark">{mark}</div>
    <h1>{title}</h1>
    <p class="sub">{sub}</p>
    <div class="pill">
      <span>{user}</span>
      <span>{host}</span>
      <span>{headline}</span>
    </div>
    {cta}
    <p class="hint">{_esc(hint)}</p>
    <p class="err" id="r3-login-err"></p>
  </div>
  <script>
    const postPath = '{post}';
    const btn = document.getElementById('r3-login-start');
    if (btn) {{
      btn.addEventListener('click', async () => {{
        btn.disabled = true;
        const err = document.getElementById('r3-login-err');
        try {{
          const r = await fetch('/api/session/start', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: '{{}}'
          }});
          const d = await r.json();
          if (!d.ok) throw new Error(d.error_de || d.message_de || 'Fehler');
          window.location.href = d.redirect || postPath;
        }} catch (e) {{
          if (err) err.textContent = e.message || String(e);
          btn.disabled = false;
        }}
      }});
    }}
  </script>
</body>
</html>"""
    return html_out.encode("utf-8")


def handle_session_start(root: Path) -> Dict[str, Any]:
    root = Path(root)
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        doc = mark_session_started(root)
        return {
            "ok": True,
            "redirect": doc.get("post_login_path") or "/desktop",
            "message_de": "R3-Sitzung gestartet (headless)",
            "session": doc,
        }
    doc = mark_session_started(root)
    return {
        "ok": True,
        "redirect": str(doc.get("post_login_path") or "/desktop"),
        "message_de": "Willkommen in R3",
        "session": doc,
    }


def handle_session_end(root: Path) -> Dict[str, Any]:
    out = end_session()
    try:
        from analytics.r3_system_plane import session_lock

        lock = session_lock()
        if lock.get("ok"):
            out["lock_de"] = lock.get("message_de")
    except Exception:
        pass
    return out
