"""R3 Weltneuheit — Launch als eigenständige Erfahrung."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/r3_launch_world.json")
_EVIDENCE_REL = Path("evidence/r3_launch_world_latest.json")


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_launch_world(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _CONFIG_REL)
    if doc:
        return doc
    return {
        "world_novelty_de": "Weltneuheit",
        "title_de": "R3 — Research neu gedacht",
        "pillars": [],
    }


def world_launch_kernel_gate(root: Path) -> Dict[str, Any]:
    """Weltneuheit nur, wenn Cognitive Kernel v2 autoritativ ist."""
    root = Path(root)
    world = load_launch_world(root)
    try:
        from analytics.linux_runtime_unified import kernel_is_authoritative, kernel_supremacy_status

        auth = kernel_is_authoritative(root)
        sup = kernel_supremacy_status(root)
    except Exception:
        auth = False
        sup = {}
    mainline = str(
        world.get("linux_mainline_de")
        or sup.get("linux_mainline_de")
        or "Der Linux-Kernel (vmlinuz) bleibt unverändert — nur die Steuerungsschicht ist R3."
    )
    share = str(world.get("share_dir_note_de") or "Daten liegen unter ~/.local/share/r3-os/.")
    gate_de = str(world.get("kernel_gate_de") or "Weltneuheit nur mit Cognitive Kernel v2.")
    return {
        "allowed": auth,
        "kernel_name_de": str(sup.get("kernel_name_de") or "Cognitive Kernel v2"),
        "reason_de": (
            f"{gate_de} Kernel aktiv."
            if auth
            else f"{gate_de} Bitte zuerst den KI-Kernel aktivieren."
        ),
        "linux_mainline_de": mainline,
        "share_dir_note_de": share,
        "activate_cmd_de": "python3 tools/ai_kernel.py cognitive-kernel",
        "cockpit_path": "/",
    }


def enrich_launch_world(launch_doc: Dict[str, Any], root: Path) -> Dict[str, Any]:
    """Launch-Status mit Weltneuheit-Narrativ anreichern."""
    root = Path(root)
    world = load_launch_world(root)
    out = dict(launch_doc)
    out["kernel_gate"] = world_launch_kernel_gate(root)
    labels = world.get("milestone_labels") or {}
    milestones = []
    for m in out.get("milestones") or []:
        mid = str(m.get("id") or "")
        row = dict(m)
        if labels.get(mid):
            row["label_de"] = labels[mid]
        milestones.append(row)
    out["milestones"] = milestones
    out["world"] = {
        "novelty_de": world.get("world_novelty_de"),
        "title_de": world.get("title_de"),
        "subtitle_de": world.get("subtitle_de"),
        "claim_de": world.get("claim_de"),
        "pillars": list(world.get("pillars") or []),
        "cta_cockpit_de": world.get("cta_cockpit_de"),
        "cta_join_de": world.get("cta_join_de"),
        "reveal_enabled": bool(world.get("reveal_enabled")),
    }
    phase = str(out.get("phase") or "")
    overall = int(out.get("overall_pct") or 0)
    if out.get("public_launch_ready"):
        out["world_headline_de"] = "Welt-Start bereit — R3 geht öffentlich."
    elif phase == "h1_running":
        h1_pct = int((out.get("h1") or {}).get("progress_pct") or 0)
        out["world_headline_de"] = f"Weltneuheit lädt — Validierung {h1_pct}%"
    else:
        out["world_headline_de"] = world.get("claim_de")
    try:
        from analytics.r3_surface_theme import sanitize_surface_text

        out["world_headline_de"] = sanitize_surface_text(str(out.get("world_headline_de") or ""))
        if out.get("headline_de"):
            out["headline_de"] = sanitize_surface_text(str(out["headline_de"]))
    except Exception:
        pass
    atomic_write_json(root / _EVIDENCE_REL, {"launch": out, "world": out["world"]})
    return out


def _pillar_html(pillars: List[Dict[str, Any]]) -> str:
    from analytics.r3_icons import icon_span

    rows = []
    for p in pillars:
        icon_name = str(p.get("icon") or "sparkle")
        rows.append(
            f"""<article class="wl-pillar">
              <div class="wl-pillar-icon">{icon_span(icon_name, cls="r3-ico r3-ico--lg")}</div>
              <h3>{_esc(p.get('title_de'))}</h3>
              <p>{_esc(p.get('body_de'))}</p>
            </article>"""
        )
    return f'<div class="wl-pillars">{"".join(rows)}</div>'


def _milestone_timeline(milestones: List[Dict[str, Any]]) -> str:
    from analytics.r3_icons import icon_span

    items = []
    for i, m in enumerate(milestones):
        done = bool(m.get("done"))
        cls = "done" if done else ""
        mark = icon_span("check", cls="r3-ico r3-ico--sm") if done else str(i + 1)
        items.append(
            f'<div class="wl-ms {cls}"><span class="wl-ms-n">{mark}</span>'
            f'<span>{_esc(m.get("label_de"))}</span></div>'
        )
    return f'<div class="wl-timeline">{"".join(items)}</div>'


from analytics.r3_icons import R3_ICON_CSS as _WL_ICON_CSS  # noqa: E402

WORLD_LAUNCH_CSS = _WL_ICON_CSS + """
.wl-page { max-width: 920px; margin: 0 auto; padding: 32px 20px 80px; }
.wl-hero {
  text-align: center; padding: 48px 24px 36px; margin-bottom: 28px;
  border-radius: var(--radius, 28px);
  background: linear-gradient(165deg, rgba(94,92,230,.2) 0%, rgba(48,213,200,.08) 40%, var(--card) 70%);
  border: 1px solid rgba(94,92,230,.28);
  box-shadow: var(--shadow);
  position: relative; overflow: hidden;
}
.wl-hero::before {
  content: ""; position: absolute; inset: -50% -20%;
  background: radial-gradient(circle at 50% 0%, rgba(94,92,230,.35), transparent 55%);
  pointer-events: none; animation: wl-pulse 8s ease-in-out infinite;
}
@keyframes wl-pulse { 0%,100% { opacity: .6; } 50% { opacity: 1; } }
.wl-badge {
  display: inline-block; font-size: 11px; font-weight: 800; letter-spacing: .2em;
  text-transform: uppercase; color: var(--accent-2, #30d5c8);
  border: 1px solid rgba(48,213,200,.4); padding: 8px 16px; border-radius: 999px;
  margin-bottom: 16px; position: relative;
}
.wl-hero h1 {
  margin: 0 0 12px; font-size: clamp(36px, 6vw, 52px); font-weight: 800;
  letter-spacing: -.04em; line-height: 1.05; position: relative;
}
.wl-hero .wl-sub { font-size: 17px; color: var(--muted); max-width: 540px; margin: 0 auto 20px; line-height: 1.5; position: relative; }
.wl-claim {
  font-size: 15px; font-weight: 600; color: var(--text); max-width: 560px; margin: 0 auto;
  padding: 14px 18px; border-radius: 16px; background: rgba(94,92,230,.12);
  border: 1px solid rgba(94,92,230,.2); position: relative;
}
.wl-ring-row {
  display: flex; justify-content: center; align-items: center; gap: 32px;
  flex-wrap: wrap; margin: 28px 0 8px; position: relative;
}
.wl-ring-big {
  width: 140px; height: 140px; border-radius: 50%;
  display: grid; place-items: center; position: relative; font-weight: 800;
  background: conic-gradient(var(--accent) calc(var(--pct) * 1%), rgba(127,127,127,.12) 0);
}
.wl-ring-big::before {
  content: ""; position: absolute; inset: 14px; border-radius: 50%; background: var(--card);
}
.wl-ring-big span { position: relative; font-size: 32px; letter-spacing: -.03em; }
.wl-ring-cap { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; margin-top: 6px; text-align: center; }
.wl-pillars { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 24px; }
@media (max-width: 720px) { .wl-pillars { grid-template-columns: 1fr; } }
.wl-pillar {
  padding: 20px 18px; border-radius: 20px; background: var(--card);
  border: 1px solid var(--line); text-align: center;
}
.wl-pillar-icon { margin-bottom: 10px; color: var(--accent); }
.wl-pillar-icon .r3-ico svg { width: 28px; height: 28px; }
.wl-pillar h3 { margin: 0 0 8px; font-size: 16px; font-weight: 700; }
.wl-pillar p { margin: 0; font-size: 13px; color: var(--muted); line-height: 1.45; }
.wl-card {
  padding: 22px 24px; border-radius: var(--radius, 24px); background: var(--card);
  border: 1px solid var(--line); box-shadow: var(--shadow); margin-bottom: 18px;
}
.wl-card h2 { margin: 0 0 14px; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.wl-bar { height: 10px; border-radius: 999px; background: rgba(127,127,127,.12); overflow: hidden; }
.wl-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-2, #30d5c8)); transition: width .6s; }
.wl-meta { display: flex; justify-content: space-between; margin-top: 8px; font-size: 13px; color: var(--muted); }
.wl-timeline { display: flex; flex-wrap: wrap; gap: 10px; }
.wl-ms {
  display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 999px;
  background: rgba(127,127,127,.08); font-size: 13px; font-weight: 600;
}
.wl-ms.done { background: rgba(50,215,75,.14); color: var(--ok); }
.wl-ms-n {
  width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center;
  font-size: 11px; background: rgba(127,127,127,.15);
}
.wl-ms.done .wl-ms-n { background: var(--ok); color: #000; }
.wl-cta { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; margin-top: 24px; }
.wl-btn {
  display: inline-block; padding: 14px 24px; border-radius: 999px; text-decoration: none;
  font-weight: 700; font-size: 15px; transition: transform .15s, box-shadow .15s;
}
.wl-btn:hover { transform: translateY(-2px); }
.wl-btn-primary {
  background: linear-gradient(135deg, var(--accent), #7d7aff); color: #fff;
  box-shadow: 0 12px 40px rgba(94,92,230,.4);
}
.wl-btn-secondary {
  background: rgba(127,127,127,.12); color: var(--text); border: 1px solid var(--line);
}
.wl-foot { text-align: center; font-size: 11px; color: var(--muted); margin-top: 24px; }
.wl-gate { text-align: center; padding: 48px 24px 36px; margin-bottom: 28px; }
.wl-gate h1 { font-size: clamp(1.6rem, 4vw, 2.2rem); margin: 12px 0; }
.wl-reveal {
  position: fixed; inset: 0; z-index: 10000; display: flex; align-items: center; justify-content: center;
  padding: 24px; background: rgba(0,0,0,.72); backdrop-filter: blur(12px);
}
.wl-reveal-card {
  max-width: 480px; padding: 36px 32px; border-radius: 28px; text-align: center;
  background: var(--card); border: 1px solid rgba(94,92,230,.3);
  box-shadow: 0 32px 100px rgba(0,0,0,.5);
}
.wl-reveal-card h2 { margin: 0 0 12px; font-size: 26px; font-weight: 800; }
.wl-reveal-card p { margin: 0 0 20px; color: var(--muted); line-height: 1.5; }
.wl-reveal-card button {
  width: 100%; padding: 16px; border: 0; border-radius: 16px; font-weight: 700; font-size: 16px;
  background: linear-gradient(135deg, var(--accent), #7d7aff); color: #fff; cursor: pointer;
}
"""


WORLD_LAUNCH_JS = """
async function refreshWorldLaunch() {
  try {
    const r = await fetch('/api/launch/status', { cache: 'no-store' });
    const d = await r.json();
    const w = d.world || {};
    const h1 = d.h1 || {};
    const overall = d.overall_pct || 0;
    const h1pct = h1.progress_pct || 0;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('wl-headline', d.world_headline_de || d.headline_de || '');
    set('wl-overall', overall + '%');
    set('wl-h1-pct', h1pct + '%');
    set('wl-h1-status', h1.status || '—');
    set('wl-h1-detail', h1.detail_de || '');
    set('wl-updated', d.updated_at_utc || '');
    const ring = document.getElementById('wl-ring');
    if (ring) ring.style.setProperty('--pct', overall);
    const fill = document.getElementById('wl-h1-fill');
    if (fill) fill.style.width = h1pct + '%';
    const tl = document.getElementById('wl-timeline');
    if (tl && Array.isArray(d.milestones)) {
      tl.innerHTML = d.milestones.map((m, i) => {
        const done = m.done ? 'done' : '';
        const mark = m.done ? '✓' : String(i + 1);
        return '<div class="wl-ms ' + done + '"><span class="wl-ms-n">' + mark + '</span><span>' + (m.label_de || '') + '</span></div>';
      }).join('');
    }
    const lt = document.getElementById('wl-tiles');
    if (lt && Array.isArray(d.tiles)) {
      lt.innerHTML = d.tiles.map(t => {
        const cls = t.ok ? 'ok' : '';
        return '<div class="lb-tile ' + cls + '"><div class="lb-tile-label">' + (t.label_de || '') + '</div>' +
          '<div class="lb-tile-value">' + (t.value_de || '') + '</div>' +
          '<div class="lb-tile-detail">' + (t.detail_de || '') + '</div></div>';
      }).join('');
    }
  } catch (e) {}
}
setInterval(refreshWorldLaunch, 10000);
(function() {
  const KEY = document.body.getAttribute('data-reveal-key');
  const ov = document.getElementById('wl-reveal');
  const btn = document.getElementById('wl-reveal-btn');
  if (!ov || !KEY) return;
  if (localStorage.getItem(KEY) === '1') { ov.remove(); return; }
  btn && btn.addEventListener('click', () => {
    localStorage.setItem(KEY, '1');
    ov.remove();
  });
})();
"""


def render_kernel_gate_section(gate: Dict[str, Any], root: Path) -> str:
    """Hinweis wenn Weltneuheit ohne KI-Kernel gesperrt ist."""
    _ = root
    allowed = bool(gate.get("allowed"))
    if allowed:
        return ""
    return f"""
<section class="wl-gate" id="world-launch-gate" aria-label="Kernel erforderlich">
  <div class="wl-badge">Kernel</div>
  <h1>Weltneuheit gesperrt</h1>
  <p class="wl-sub">{_esc(gate.get('reason_de'))}</p>
  <p class="wl-claim">{_esc(gate.get('kernel_name_de'))} muss aktiv sein, bevor die Weltneuheit startet.</p>
  <div class="wl-card" style="text-align:left;margin-top:24px">
    <p><strong>Linux bleibt Linux:</strong> {_esc(gate.get('linux_mainline_de'))}</p>
    <p style="margin-top:12px">{_esc(gate.get('share_dir_note_de'))}</p>
    <p style="margin-top:16px;font-family:ui-monospace,monospace;font-size:13px">{_esc(gate.get('activate_cmd_de'))}</p>
  </div>
  <div class="wl-cta">
    <a class="wl-btn wl-btn-primary" href="/">Zum Cockpit</a>
  </div>
</section>"""


def render_world_launch_section(launch_doc: Dict[str, Any], root: Path) -> str:
    gate = launch_doc.get("kernel_gate") or world_launch_kernel_gate(root)
    if not gate.get("allowed"):
        return render_kernel_gate_section(gate, root)
    world = launch_doc.get("world") or load_launch_world(root)
    overall = int(launch_doc.get("overall_pct") or 0)
    h1 = launch_doc.get("h1") or {}
    h1_pct = int(h1.get("progress_pct") or 0)
    headline = launch_doc.get("world_headline_de") or launch_doc.get("headline_de") or world.get("claim_de")
    milestones = launch_doc.get("milestones") or []
    tiles_html = ""
    try:
        from analytics.preview_status_visual import render_launch_tiles_row

        tiles_html = render_launch_tiles_row(list(launch_doc.get("tiles") or []))
        tiles_html = tiles_html.replace('id="lb-tiles"', 'id="wl-tiles"')
    except Exception:
        pass
    cfg = load_launch_world(root)
    reveal_enabled = bool(cfg.get("reveal_enabled"))
    reveal_html = ""
    if reveal_enabled:
        reveal = world.get("reveal") if isinstance(world.get("reveal"), dict) else {}
        if not reveal:
            reveal = {
                "storage_key": cfg.get("storage_key"),
                "title_de": cfg.get("reveal_title_de"),
                "body_de": cfg.get("reveal_body_de"),
                "button_de": cfg.get("reveal_button_de"),
            }
        reveal_html = f"""
<div id="wl-reveal" class="wl-reveal" role="dialog" aria-modal="true">
  <div class="wl-reveal-card">
    <div class="wl-badge">{_esc(world.get('novelty_de') or 'Weltneuheit')}</div>
    <h2>{_esc(reveal.get('title_de'))}</h2>
    <p>{_esc(reveal.get('body_de'))}</p>
    <button type="button" id="wl-reveal-btn">{_esc(reveal.get('button_de'))}</button>
  </div>
</div>"""
    return f"""
<section class="wl-hero" id="world-launch" aria-label="Weltneuheit">
  <div class="wl-badge">{_esc(world.get('novelty_de') or 'Weltneuheit')}</div>
  <h1>{_esc(world.get('title_de'))}</h1>
  <p class="wl-sub">{_esc(world.get('subtitle_de'))}</p>
  <p class="wl-claim" id="wl-headline">{_esc(headline)}</p>
  <div class="wl-ring-row">
    <div>
      <div class="wl-ring-big" id="wl-ring" style="--pct:{overall}">
        <span id="wl-overall">{overall}%</span>
      </div>
      <div class="wl-ring-cap">Welt-Start</div>
    </div>
  </div>
  <div class="wl-cta">
    <a class="wl-btn wl-btn-primary" href="#cockpit">{_esc(world.get('cta_cockpit_de') or 'Cockpit öffnen')}</a>
    <a class="wl-btn wl-btn-secondary" href="/join">{_esc(world.get('cta_join_de') or 'Mitwirken')}</a>
  </div>
</section>
{_pillar_html(list(world.get('pillars') or []))}
<div class="wl-card">
  <h2>Validierung</h2>
  <div class="wl-bar"><div class="wl-fill" id="wl-h1-fill" style="width:{h1_pct}%"></div></div>
  <div class="wl-meta"><span id="wl-h1-status">{_esc(h1.get('status'))}</span><span id="wl-h1-pct">{h1_pct}%</span></div>
  <p class="wl-sub" id="wl-h1-detail" style="margin-top:12px;text-align:left">{_esc(h1.get('detail_de'))}</p>
</div>
<div class="wl-card">
  <h2>Infrastruktur</h2>
  {tiles_html}
</div>
<div class="wl-card">
  <h2>Zeitleiste</h2>
  <div id="wl-timeline">{_milestone_timeline(milestones)}</div>
</div>
<p class="wl-foot">Live · <span id="wl-updated">{_esc(launch_doc.get('updated_at_utc'))}</span></p>
{reveal_html}"""


def render_world_launch_page(launch_doc: Dict[str, Any], root: Path, *, port: int = 17890) -> bytes:
    """Dedizierte Weltneuheit-Seite unter /launch — nur mit aktivem KI-Kernel."""
    root = Path(root)
    gate = launch_doc.get("kernel_gate") or world_launch_kernel_gate(root)
    if not gate.get("allowed"):
        return render_world_launch_blocked_page(root, gate, port=port)
    world = launch_doc.get("world") or load_launch_world(root)
    storage_key = str((world.get("reveal") or {}).get("storage_key") or "r3_world_launch_seen_v1")
    try:
        from analytics.r3_surface_theme import R3_CSS_ROOT, render_nav, surface_title

        title = surface_title(root) + " · Weltneuheit"
        nav = render_nav(root, active="launch")
        r3_css = R3_CSS_ROOT
    except Exception:
        title = "R3 · Weltneuheit"
        nav = ""
        r3_css = ""
    try:
        from analytics.preview_status_visual import SYSTEM_STATUS_CSS
    except Exception:
        SYSTEM_STATUS_CSS = ""
    body = render_world_launch_section(launch_doc, root)
    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="color-scheme" content="light dark"/>
<title>{_esc(title)}</title>
<style>
{r3_css}
{WORLD_LAUNCH_CSS}
{SYSTEM_STATUS_CSS}
</style>
</head>
<body data-reveal-key="{_esc(storage_key)}">
<div class="wl-page">
{nav}
{body}
<div class="wl-cta">
  <a class="wl-btn wl-btn-primary" href="/">Cockpit — volle Kontrolle</a>
</div>
</div>
<script>{WORLD_LAUNCH_JS}</script>
</body>
</html>"""
    return page.encode("utf-8")


def render_world_launch_blocked_page(root: Path, gate: Dict[str, Any], *, port: int = 17890) -> bytes:
    """/launch ohne KI-Kernel — Sperrseite statt Weltneuheit."""
    _ = port
    root = Path(root)
    try:
        from analytics.r3_surface_theme import R3_CSS_ROOT, render_nav, surface_title

        title = surface_title(root) + " · Kernel erforderlich"
        nav = render_nav(root, active="launch")
        r3_css = R3_CSS_ROOT
    except Exception:
        title = "R3 · Kernel erforderlich"
        nav = ""
        r3_css = ""
    body = render_kernel_gate_section(gate, root)
    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="color-scheme" content="light dark"/>
<title>{_esc(title)}</title>
<style>
{r3_css}
{WORLD_LAUNCH_CSS}
</style>
</head>
<body>
<div class="wl-page">
{nav}
{body}
</div>
</body>
</html>"""
    return page.encode("utf-8")
