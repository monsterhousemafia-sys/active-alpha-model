"""Apple-inspiriertes HTML-Visual für GUI Preview — eine Datei, kein CDN."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

_HTML_REL = Path("evidence/gui_preview_latest.html")
_HOME_REL = Path(".local/share/r3-os/gui_preview_latest.html")


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _surface(text: Any) -> str:
    try:
        from analytics.r3_surface_theme import sanitize_surface_text

        return sanitize_surface_text(str(text or ""))
    except Exception:
        return str(text or "")


def _step_status(step: Dict[str, Any]) -> Tuple[str, str]:
    if step.get("pass"):
        return "ok", "OK"
    if step.get("partial"):
        return "warn", "Läuft"
    return "fail", "Fehler"


def _parse_circle(report: Dict[str, Any]) -> Tuple[int, int, int]:
    for s in report.get("backend_steps") or []:
        if s.get("id") != "circle_score":
            continue
        m = re.search(r"(\d+)/(\d+)", str(s.get("detail_de") or ""))
        if m:
            g, t = int(m.group(1)), int(m.group(2))
            return g, t, int(round(100 * g / max(t, 1)))
    try:
        chat = report.get("chat_evolution") or {}
        # fallback from refreshed circle in evolve path — optional
    except Exception:
        pass
    return 0, 6, 0


def _format_time_de(iso_utc: str) -> str:
    try:
        ts = datetime.fromisoformat(str(iso_utc).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            from datetime import timezone

            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y · %H:%M")
    except (TypeError, ValueError):
        return str(iso_utc or "—")


def _ring_svg(pct: int, *, size: int = 120) -> str:
    pct = max(0, min(100, int(pct)))
    r = 46
    c = 2 * 3.14159265 * r
    dash = c * pct / 100.0
    color = "#34c759" if pct >= 80 else "#ff9f0a" if pct >= 40 else "#ff3b30"
    return f"""
    <svg width="{size}" height="{size}" viewBox="0 0 120 120" aria-hidden="true">
      <circle cx="60" cy="60" r="{r}" fill="none" stroke="rgba(0,0,0,.06)" stroke-width="10"/>
      <circle cx="60" cy="60" r="{r}" fill="none" stroke="{color}" stroke-width="10"
        stroke-linecap="round" stroke-dasharray="{dash:.1f} {c:.1f}"
        transform="rotate(-90 60 60)"/>
    </svg>"""


def _circle_dots(green: int, total: int) -> str:
    dots = []
    for i in range(total):
        cls = "on" if i < green else "off"
        dots.append(f'<span class="dot {cls}"></span>')
    return "".join(dots)


def _render_steps(steps: List[Dict[str, Any]]) -> str:
    if not steps:
        return ""
    rows = []
    for s in steps:
        st, label = _step_status(s)
        rows.append(
            f"""
            <li class="row {st}">
              <div class="row-head">
                <span class="pill {st}">{_esc(label)}</span>
                <span class="row-title">{_esc(s.get('label_de'))}</span>
              </div>
              <p class="row-detail">{_esc(_surface(s.get('detail_de')))}</p>
            </li>"""
        )
    return f'<ul class="rows">{"".join(rows)}</ul>'


def _render_manifest_overlay(manifest: Dict[str, Any]) -> str:
    if not manifest.get("required_read", True):
        return ""
    key = _esc(manifest.get("storage_key") or "aa_manifest_v1_ack")
    title = _esc(manifest.get("title_de") or "R3")
    one = _esc(manifest.get("one_liner_de") or "")
    btn = _esc(manifest.get("ack_button_de") or "Gelesen")
    from analytics.preview_manifest import manifest_sections_html

    blocks = manifest_sections_html(list(manifest.get("sections") or []))
    community = _esc(manifest.get("community_de") or "")
    return f"""
    <div id="manifest-overlay" class="manifest-overlay" role="dialog" aria-modal="true" aria-labelledby="mf-title">
      <div class="manifest-card">
        <div class="mf-brand">R3 · Offenes Research</div>
        <h2 id="mf-title">{title}</h2>
        <p class="mf-lead">{one}</p>
        <div class="mf-blocks">{blocks}</div>
        <p class="mf-community">{community}</p>
        <button type="button" id="manifest-ack" class="mf-ack">{btn}</button>
        <p class="mf-hint">Einmal lesen — danach öffnet sich das Cockpit.</p>
      </div>
    </div>
    <script>
    (function() {{
      const KEY = "{key}";
      const ov = document.getElementById("manifest-overlay");
      const btn = document.getElementById("manifest-ack");
      if (!ov) return;
      if (localStorage.getItem(KEY) === "1") {{
        ov.remove();
        return;
      }}
      document.body.classList.add("manifest-locked");
      btn.addEventListener("click", () => {{
        localStorage.setItem(KEY, "1");
        ov.remove();
        document.body.classList.remove("manifest-locked");
      }});
    }})();
    </script>"""


def _render_federation(fed: Dict[str, Any]) -> str:
    if not fed or not fed.get("enabled", True):
        return ""
    workers = fed.get("workers") or []
    rows = []
    for w in workers:
        role = _esc(w.get("role") or "compute")
        host = _esc(w.get("hostname") or w.get("worker_id") or "—")
        cpus = int(w.get("cpus") or 0)
        ok = "✓" if w.get("preview_ok") else "○"
        h1 = " · H1" if w.get("h1_running") else ""
        rows.append(
            f"<li><strong>{host}</strong> <span class='muted'>({role})</span> — "
            f"{cpus} Kerne · Preview {ok}{h1}</li>"
        )
    join_url = _esc(fed.get("join_url") or "")
    share_url = _esc(fed.get("share_url") or "")
    worker_list = "".join(rows) if rows else "<li class='muted'>Noch keine Worker — Link teilen</li>"
    return f"""
    <section class="card" id="federation">
      <h2>Zentrale Rechenleistung</h2>
      <p class="subtitle">{_esc(_surface(fed.get('headline_de')))}</p>
      <div class="metrics">
        <div class="metric"><b>{int(fed.get('workers_online') or 0)}</b><span>Knoten</span></div>
        <div class="metric"><b>{int(fed.get('total_cpus') or 0)}</b><span>CPU-Kerne</span></div>
        <div class="metric"><b>{int(fed.get('preview_ok_nodes') or 0)}</b><span>Preview OK</span></div>
      </div>
      <ul class="order-lines">{worker_list}</ul>
      <p class="hub-note">Preview teilen: andere Rechner öffnen <code>/join</code> und starten den Worker.</p>
      <div class="actions">
        <button type="button" class="act primary" id="copy-share">Share-Link kopieren</button>
        <button type="button" class="act secondary" id="copy-join">Join-Link kopieren</button>
      </div>
      <input type="hidden" id="share-url" value="{share_url}">
      <input type="hidden" id="join-url" value="{join_url}">
    </section>
    <script>
    (function() {{
      function copyVal(id, label) {{
        const el = document.getElementById(id);
        if (!el || !el.value) return;
        navigator.clipboard.writeText(el.value).then(() => {{
          const toast = document.getElementById("toast");
          if (toast) {{
            toast.hidden = false;
            toast.className = "toast ok";
            toast.textContent = label + " kopiert: " + el.value;
            setTimeout(() => {{ toast.hidden = true; }}, 6000);
          }}
        }}).catch(() => alert(el.value));
      }}
      const cs = document.getElementById("copy-share");
      const cj = document.getElementById("copy-join");
      if (cs) cs.addEventListener("click", () => copyVal("share-url", "Share-Link"));
      if (cj) cj.addEventListener("click", () => copyVal("join-url", "Join-Link"));
    }})();
    </script>"""


def _render_cockpit(cockpit: Dict[str, Any], hub_port: int) -> str:
    if not cockpit:
        return ""
    tc = _esc(cockpit.get("traffic_class") or "warn")
    traffic = _esc(cockpit.get("traffic") or "—")
    actions = cockpit.get("actions") or []
    action_btns = []
    for a in actions:
        tier = str(a.get("tier") or "secondary")
        action_btns.append(
            f"""<button type="button" class="act {tier}" data-action="{_esc(a.get('id'))}" title="{_esc(a.get('detail_de'))}">
              <span class="act-label">{_esc(a.get('label_de'))}</span>
              <span class="act-detail">{_esc(a.get('detail_de'))}</span>
            </button>"""
        )
    po = cockpit.get("portfolio_orders") or {}
    order_lines = "".join(f"<li>{_esc(ln)}</li>" for ln in (po.get("lines_de") or [])[:8])
    rb = cockpit.get("rebalance") or {}
    warn = cockpit.get("warnings") or {}
    learn = cockpit.get("learning") or {}
    stale_banner = ""
    if cockpit.get("preview_stale"):
        stale_banner = f'<div class="notice warn">{_esc(cockpit.get("preview_stale_de") or "Daten veraltet")}</div>'
    return f"""
    <section class="card card-command" id="cockpit">
      {stale_banner}
      <div class="cmd-head">
        <h2>Handel heute</h2>
        <span class="traffic {tc}">{traffic}</span>
      </div>
      <p class="cmd-action">{_esc(cockpit.get('today_action_de'))}</p>
      <div class="cmd-metrics">
        <div class="metric"><b>{_esc(cockpit.get('cash_de'))}</b><span>Guthaben</span></div>
        <div class="metric"><b>{int(cockpit.get('n_positions') or 0)}</b><span>Positionen</span></div>
        <div class="metric"><b>{_esc(learn.get('grade'))}</b><span>Lernen</span></div>
      </div>
      <div class="cmd-grid">
        <div class="cmd-block">
          <h3>Rebalance</h3>
          <p>{_esc(rb.get('summary_de'))}</p>
          <p class="muted">{int(rb.get('recorded_days') or 0)}/{int(rb.get('every_days') or 5)} Tage · { 'fällig' if rb.get('is_due') else 'nicht fällig' }</p>
        </div>
        <div class="cmd-block">
          <h3>Orders geplant</h3>
          <p>{_esc(po.get('summary_de'))}</p>
          {"<ul class='order-lines'>" + order_lines + "</ul>" if order_lines else ""}
        </div>
        <div class="cmd-block">
          <h3>Warnungen</h3>
          <p>{_esc(warn.get('headline_de'))}</p>
          <p class="muted">{int(warn.get('critical_count') or 0)}× kritisch · Queue: {_esc(cockpit.get('deferred_de'))}</p>
        </div>
      </div>
      <p class="hub-note">{_esc(cockpit.get('hub_note_de'))}</p>
      <div class="actions" id="actions">{"".join(action_btns)}</div>
      <div class="toast" id="toast" hidden></div>
    </section>
    <script>
    (function() {{
      const HUB = (window.location.protocol === "http:" || window.location.protocol === "https:")
        ? window.location.origin
        : "http://127.0.0.1:{int(hub_port)}";
      const toast = document.getElementById("toast");
      function showToast(msg, ok) {{
        if (!toast) return;
        toast.hidden = false;
        toast.className = "toast " + (ok ? "ok" : "fail");
        toast.textContent = msg;
        setTimeout(() => {{ toast.hidden = true; }}, 8000);
      }}
      async function runAction(id) {{
        showToast("Läuft: " + id + " …", true);
        try {{
          const r = await fetch(HUB + "/api/action", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ action: id }}),
          }});
          const j = await r.json();
          showToast(j.message_de || (j.ok ? "OK" : "Fehler"), !!j.ok);
          if (j.reload) location.reload();
          else if (j.ok && id !== "order-desk") {{
            const c = await fetch(HUB + "/api/cockpit");
            const ck = await c.json();
            const el = document.querySelector("#cockpit .cmd-action");
            if (el && ck.today_action_de) el.textContent = ck.today_action_de;
            if (typeof refreshSystemStatus === "function") refreshSystemStatus();
          }}
        }} catch (e) {{
          showToast("Hub nicht erreichbar — r3-cockpit erneut starten", false);
        }}
      }}
      document.querySelectorAll("[data-action]").forEach(btn => {{
        btn.addEventListener("click", () => runAction(btn.getAttribute("data-action")));
      }});
    }})();
    </script>"""


def render_gui_preview_html(report: Dict[str, Any], *, hub_port: int = 17890) -> str:
    passed = int(report.get("passed") or 0)
    total = int(report.get("total") or 0)
    score_pct = int(round(100 * passed / max(total, 1)))
    overall = bool(report.get("overall_pass"))
    circle_g, circle_t, circle_pct = _parse_circle(report)
    when = _format_time_de(str(report.get("generated_at_utc") or ""))
    mode = _esc(report.get("mode") or "stable")
    system_status = report.get("system_status") or {}
    chat = report.get("chat_evolution") or {}
    chat_lines = [ln.strip() for ln in str(chat.get("chat_reply_de") or "").splitlines() if ln.strip()][:6]
    next_step = str(chat.get("next_step_de") or "").strip()
    probes = report.get("widget_probes") or {}
    blockers = report.get("blockers") or []
    partial_ids = [
        s.get("id")
        for s in (report.get("backend_steps") or []) + (report.get("chat_steps") or []) + (report.get("gui_steps") or [])
        if s.get("partial") and not s.get("pass")
    ]
    llm = (chat.get("llm_health") or {}).get("resolved_model") or "—"
    hero_status = "Bereit" if overall else "Aktion nötig"
    hero_class = "hero-ok" if overall else "hero-fail"

    sections = [
        ("Diagnose · Daten", "backend_steps"),
        ("Assistent", "chat_steps"),
        ("Oberfläche", "gui_steps"),
    ]
    section_html = []
    for title, key in sections:
        body = _render_steps(list(report.get(key) or []))
        if body:
            section_html.append(
                f'<section class="card"><h2>{_esc(title)}</h2>{body}</section>'
            )

    probe_items = "".join(
        f'<div class="probe"><span class="probe-k">{_esc(k)}</span><span class="probe-v">{_esc(str(v)[:180])}</span></div>'
        for k, v in list(probes.items())[:8]
    )

    chat_block = ""
    if not system_status.get("ki_next") and (chat_lines or next_step):
        lines_html = "".join(f"<p>{_esc(ln)}</p>" for ln in chat_lines)
        nxt = f'<p class="next-step">{_esc(next_step)}</p>' if next_step else ""
        chat_block = f"""
        <section class="card card-accent">
          <h2>Nächster Schritt</h2>
          <div class="chat-body">{lines_html}{nxt}</div>
          <p class="meta-line">Assistent · {_esc(llm)}</p>
        </section>"""

    notice = ""
    if partial_ids:
        notice = f'<div class="notice warn">Hinweis: {", ".join(_esc(x) for x in partial_ids)} — kein Blocker</div>'
    if blockers:
        notice += f'<div class="notice fail">Blocker: {", ".join(_esc(x) for x in blockers)}</div>'

    screenshot = report.get("screenshot")
    shot_block = ""
    has_shot = bool(screenshot and Path(str(screenshot)).is_file())
    if not has_shot and report.get("screenshot_default"):
        has_shot = Path(str(report.get("screenshot_default"))).is_file()
    if has_shot:
        shot_block = """
        <section class="card">
          <h2>Dashboard</h2>
          <img class="shot" src="/api/screenshot" alt="Dashboard Screenshot"/>
        </section>"""

    status_block = ""
    status_css = ""
    status_js = ""
    root = Path(__file__).resolve().parents[1]
    page_header = ""
    r3_css = ""
    nav_html = ""
    page_title = "R3 · Cockpit"
    footer_de = "Orders nur mit Bestätigung · R3 Cockpit"
    try:
        from analytics.r3_surface_theme import R3_CSS_ROOT, load_surface_identity, render_nav, render_page_header, surface_title

        ident = load_surface_identity(root)
        page_title = surface_title(root)
        footer_de = str(ident.get("footer_de") or footer_de)
        page_header = render_page_header(root, chip=str(report.get("mode") or "live"))
        r3_css = R3_CSS_ROOT
        nav_html = render_nav(root, active="home")
    except Exception:
        page_header = '<header class="r3-top"><div class="r3-mark">R3</div></header>'

    if system_status:
        from analytics.preview_status_visual import (
            SYSTEM_STATUS_CSS,
            SYSTEM_STATUS_JS,
            render_system_status_section,
        )

        status_block = render_system_status_section(system_status, root=root)
        status_css = SYSTEM_STATUS_CSS
        status_js = SYSTEM_STATUS_JS

    shell_block = ""
    shell_css = ""
    shell_js = ""
    try:
        from analytics.r3_ubuntu_shell import SHELL_CSS, SHELL_JS

        shell_css = SHELL_CSS
        shell_js = SHELL_JS
    except Exception:
        pass
    try:
        from analytics.r3_ubuntu_shell import render_ubuntu_shell_section

        shell_block = render_ubuntu_shell_section(root)
    except Exception:
        shell_block = ""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="color-scheme" content="light dark"/>
  <title>{_esc(page_title)}</title>
  <style>
    {r3_css}
    :root {{
      --radius: 24px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
        "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      -webkit-font-smoothing: antialiased;
      line-height: 1.45;
    }}
    .page {{
      max-width: 980px;
      margin: 0 auto;
      padding: 48px 24px 80px;
    }}
    .r3-top {{
      display: flex; align-items: flex-start; justify-content: space-between;
      gap: 16px; margin-bottom: 18px;
    }}
    .r3-tagline {{ margin: 6px 0 0; font-size: 14px; color: var(--muted); }}
    .hero {{
      display: grid;
      grid-template-columns: 1.2fr .8fr;
      gap: 20px;
      margin-bottom: 24px;
    }}
    @media (max-width: 760px) {{ .hero {{ grid-template-columns: 1fr; }} }}
    .card {{
      background: var(--card);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 24px 26px;
    }}
    .card-accent {{
      border-color: rgba(0,113,227,.18);
      background: linear-gradient(180deg, rgba(0,113,227,.06), var(--card));
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(32px, 5vw, 48px);
      font-weight: 700;
      letter-spacing: -.03em;
    }}
    .subtitle {{ color: var(--muted); margin: 0 0 18px; font-size: 15px; }}
    .hero-ok .status {{ color: var(--ok); }}
    .hero-fail .status {{ color: var(--fail); }}
    .status {{ font-size: 22px; font-weight: 600; margin: 0; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-top: 18px;
    }}
    .metric {{
      padding: 14px 12px;
      border-radius: 16px;
      background: rgba(0,0,0,.03);
      text-align: center;
    }}
    @media (prefers-color-scheme: dark) {{ .metric {{ background: rgba(255,255,255,.04); }} }}
    .metric b {{ display: block; font-size: 22px; font-weight: 700; }}
    .metric span {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }}
    .ring-wrap {{ display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; }}
    .ring-label {{ font-size: 28px; font-weight: 700; margin-top: -92px; }}
    .ring-sub {{ color: var(--muted); font-size: 13px; margin-top: 44px; }}
    .dots {{ display: flex; gap: 8px; justify-content: center; margin-top: 8px; }}
    .dot {{
      width: 12px; height: 12px; border-radius: 50%;
      background: var(--line);
    }}
    .dot.on {{ background: var(--ok); box-shadow: 0 0 0 4px rgba(52,199,89,.15); }}
    h2 {{
      margin: 0 0 14px;
      font-size: 13px;
      letter-spacing: .06em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 700;
    }}
    .grid {{ display: grid; gap: 18px; }}
    .rows {{ list-style: none; margin: 0; padding: 0; }}
    .row {{
      padding: 14px 0;
      border-top: 1px solid var(--line);
    }}
    .row:first-child {{ border-top: 0; padding-top: 0; }}
    .row-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
    .row-title {{ font-weight: 600; font-size: 15px; }}
    .row-detail {{ margin: 0; color: var(--muted); font-size: 14px; white-space: pre-wrap; }}
    .pill {{
      font-size: 11px;
      font-weight: 700;
      padding: 4px 8px;
      border-radius: 999px;
      letter-spacing: .04em;
      text-transform: uppercase;
    }}
    .pill.ok {{ background: rgba(52,199,89,.14); color: var(--ok); }}
    .pill.warn {{ background: rgba(255,159,10,.16); color: var(--warn); }}
    .pill.fail {{ background: rgba(255,59,48,.14); color: var(--fail); }}
    .probe {{
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 10px;
      padding: 10px 0;
      border-top: 1px solid var(--line);
      font-size: 13px;
    }}
    .probe:first-child {{ border-top: 0; }}
    .probe-k {{ color: var(--muted); }}
    .chat-body p {{ margin: 0 0 10px; font-size: 15px; }}
    .next-step {{
      margin-top: 12px !important;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(0,113,227,.08);
      color: var(--text);
      font-weight: 600;
    }}
    .meta-line {{ margin: 14px 0 0; font-size: 12px; color: var(--muted); }}
    .notice {{
      margin: 0 0 16px;
      padding: 12px 14px;
      border-radius: 14px;
      font-size: 14px;
    }}
    .notice.warn {{ background: rgba(255,159,10,.12); color: var(--warn); }}
    .notice.fail {{ background: rgba(255,59,48,.12); color: var(--fail); }}
    .shot {{
      width: 100%;
      border-radius: 16px;
      border: 1px solid var(--line);
    }}
    footer {{
      margin-top: 28px;
      text-align: center;
      color: var(--muted);
      font-size: 12px;
    }}
    .card-command {{ border-color: rgba(0,113,227,.22); }}
    .cmd-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .traffic {{
      font-size: 12px; font-weight: 700; padding: 6px 12px; border-radius: 999px;
      letter-spacing: .04em; text-transform: uppercase;
    }}
    .traffic.ok {{ background: rgba(52,199,89,.14); color: var(--ok); }}
    .traffic.warn {{ background: rgba(255,159,10,.16); color: var(--warn); }}
    .traffic.fail {{ background: rgba(255,59,48,.14); color: var(--fail); }}
    .cmd-action {{ font-size: 16px; font-weight: 600; margin: 0 0 14px; }}
    .cmd-metrics {{ margin-bottom: 16px; }}
    .cmd-grid {{
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px;
    }}
    @media (max-width: 760px) {{ .cmd-grid {{ grid-template-columns: 1fr; }} }}
    .cmd-block {{
      padding: 12px 14px; border-radius: 14px; background: rgba(0,0,0,.03); font-size: 13px;
    }}
    @media (prefers-color-scheme: dark) {{ .cmd-block {{ background: rgba(255,255,255,.04); }} }}
    .cmd-block h3 {{ margin: 0 0 8px; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }}
    .cmd-block p {{ margin: 0 0 6px; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .order-lines {{ margin: 8px 0 0; padding-left: 18px; color: var(--muted); font-size: 12px; }}
    .hub-note {{ font-size: 12px; color: var(--muted); margin: 0 0 14px; }}
    .actions {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    @media (max-width: 560px) {{ .actions {{ grid-template-columns: 1fr; }} }}
    .act {{
      display: flex; flex-direction: column; align-items: flex-start; gap: 4px;
      padding: 12px 14px; border-radius: 14px; border: 1px solid var(--line);
      background: rgba(0,0,0,.02); cursor: pointer; text-align: left;
      font-family: inherit; color: var(--text); transition: transform .12s ease, box-shadow .12s ease;
    }}
    .act:hover {{ transform: translateY(-1px); box-shadow: 0 8px 24px rgba(0,0,0,.08); }}
    .act.primary {{ border-color: rgba(0,113,227,.25); background: rgba(0,113,227,.06); }}
    .act.accent {{ border-color: rgba(52,199,89,.3); background: rgba(52,199,89,.08); }}
    .act-label {{ font-weight: 700; font-size: 14px; }}
    .act-detail {{ font-size: 12px; color: var(--muted); }}
    .toast {{
      margin-top: 12px; padding: 12px 14px; border-radius: 12px; font-size: 14px;
    }}
    .toast.ok {{ background: rgba(52,199,89,.12); color: var(--ok); }}
    .toast.fail {{ background: rgba(255,59,48,.12); color: var(--fail); }}
    body.manifest-locked {{ overflow: hidden; }}
    .manifest-overlay {{
      position: fixed; inset: 0; z-index: 9999; background: rgba(0,0,0,.55);
      display: flex; align-items: center; justify-content: center; padding: 20px;
      backdrop-filter: blur(8px);
    }}
    .manifest-card {{
      max-width: 640px; max-height: 90vh; overflow: auto;
      background: var(--card); border-radius: 24px; padding: 28px 30px;
      box-shadow: 0 24px 80px rgba(0,0,0,.25); border: 1px solid var(--line);
    }}
    .mf-brand {{
      font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
      color: var(--accent); margin-bottom: 8px;
    }}
    .mf-lead {{ font-size: 17px; line-height: 1.45; margin: 0 0 18px; color: var(--text); }}
    .mf-blocks {{ display: grid; gap: 12px; margin-bottom: 16px; }}
    .mf-block {{
      padding: 12px 14px; border-radius: 14px; background: rgba(0,113,227,.06);
      border: 1px solid rgba(0,113,227,.12);
    }}
    .mf-block h3 {{ margin: 0 0 6px; font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }}
    .mf-block p {{ margin: 0; font-size: 14px; line-height: 1.45; }}
    .mf-community {{ font-size: 13px; color: var(--muted); margin: 0 0 16px; }}
    .mf-ack {{
      width: 100%; padding: 14px 18px; border: 0; border-radius: 14px;
      background: var(--accent); color: #fff; font-weight: 700; font-size: 15px;
      cursor: pointer; font-family: inherit;
    }}
    .mf-hint {{ text-align: center; font-size: 12px; color: var(--muted); margin: 12px 0 0; }}
    footer a {{ color: var(--accent); }}
    {status_css}
    {shell_css}
  </style>
</head>
<body>
  <div class="page">
    {page_header}
    {nav_html}
    {notice}
    {shell_block}
    {status_block}

    <div class="hero">
      <section class="card {hero_class}">
        <h1>Systemcheck</h1>
        <p class="subtitle">{when} · {passed}/{total} Checks</p>
        <p class="status">{_esc(hero_status)}</p>
        <div class="metrics">
          <div class="metric"><b>{passed}</b><span>Bestanden</span></div>
          <div class="metric"><b>{circle_g}/{circle_t}</b><span>Kreis</span></div>
          <div class="metric"><b>{score_pct}%</b><span>Score</span></div>
        </div>
      </section>
      <section class="card ring-wrap">
        <div>{_ring_svg(score_pct)}</div>
        <div class="ring-label">{score_pct}%</div>
        <div class="ring-sub">Gesundheit</div>
        <div class="dots">{_circle_dots(circle_g, circle_t)}</div>
      </section>
    </div>

    {_render_federation(report.get("federation") or {})}

    {_render_cockpit(report.get("cockpit") or {}, hub_port)}

    {chat_block}

    <div class="grid">
      {"".join(section_html)}
      {"<section class='card'><h2>Widget-Vorschau</h2>" + probe_items + "</section>" if probe_items else ""}
      {shot_block}
    </div>

    <footer>{_esc(footer_de)} · <a href="#" id="manifest-reopen">Mission</a></footer>
  </div>
  {_render_manifest_overlay(report.get("manifest") or {})}
  <script>
  document.getElementById("manifest-reopen")?.addEventListener("click", (e) => {{
    e.preventDefault();
    localStorage.removeItem("{_esc((report.get('manifest') or {}).get('storage_key') or 'aa_manifest_v1_ack')}");
    location.reload();
  }});
  {status_js}
  {shell_js}
  </script>
</body>
</html>"""


def write_gui_preview_html(root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    root = Path(root)
    text = render_gui_preview_html(report)
    paths: Dict[str, str] = {}
    for rel in (_HTML_REL,):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths["html"] = str(path)
    home = Path.home() / _HOME_REL
    home.parent.mkdir(parents=True, exist_ok=True)
    home.write_text(text, encoding="utf-8")
    paths["home_html"] = str(home)
    return paths


def load_and_render_html(root: Path) -> Optional[str]:
    path = Path(root) / "evidence/gui_preview_latest.json"
    if not path.is_file():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        return render_gui_preview_html(report)
    except (json.JSONDecodeError, OSError):
        return None
