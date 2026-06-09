"""Launch-Streifen in Preview-Seite einbetten."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict

from analytics.preview_status_visual import SYSTEM_STATUS_CSS, render_launch_tiles_row


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def render_launch_embed_strip(doc: Dict[str, Any]) -> str:
    overall = int(doc.get("overall_pct") or 0)
    h1 = doc.get("h1") or {}
    h1_pct = int(h1.get("progress_pct") or 0)
    milestones = doc.get("milestones") or []
    ms_html = "".join(
        f'<span class="{"done" if m.get("done") else ""}">{_esc(m.get("label_de"))}</span>'
        for m in milestones
    )
    blockers = doc.get("blockers_de") or []
    blocker = ""
    if blockers:
        blocker = f'<p class="lb-block">{_esc(blockers[0])}</p>'

    return f"""
<section class="launch-board" id="launch-board" aria-label="Launch-Fortschritt">
  <div class="lb-top">
    <div>
      <div class="lb-eyebrow">Bereitstellung</div>
      <h2 class="lb-title" id="lb-headline">{_esc(doc.get("headline_de"))}</h2>
    </div>
    <div class="lb-ring" id="lb-ring" style="--pct:{overall}">
      <span id="lb-overall">{overall}%</span>
    </div>
  </div>
  <div class="lb-h1">
    <div class="lb-h1-meta"><span>Validierung · <span id="lb-h1-status">{_esc(h1.get("status"))}</span></span><span id="lb-h1-pct">{h1_pct}%</span></div>
    <div class="lb-bar"><div class="lb-fill" id="lb-h1-fill" style="width:{h1_pct}%"></div></div>
    <p class="lb-detail" id="lb-h1-detail">{_esc(h1.get("detail_de"))}</p>
  </div>
  {render_launch_tiles_row(list(doc.get("tiles") or []))}
  <div class="lb-ms" id="lb-milestones">{ms_html}</div>
  {blocker}
  <p class="lb-updated">Aktualisiert: <span id="lb-updated">{_esc(doc.get("updated_at_utc"))}</span></p>
</section>"""


LAUNCH_EMBED_CSS = """
.hub-nav {{
  display:flex; justify-content:center; gap:8px; margin-bottom:16px; flex-wrap:wrap;
}}
.hub-nav a {{
  padding:8px 14px; border-radius:999px; text-decoration:none; font-size:13px; font-weight:600;
  background: rgba(127,127,127,0.12); color: var(--text);
}}
.hub-nav a.active {{ background: var(--accent); color:#fff; }}
.launch-board {{
  margin-bottom: 22px; padding: 20px 22px; border-radius: 22px;
  border: 1px solid rgba(0,113,227,.18);
  background: linear-gradient(180deg, rgba(0,113,227,.07), var(--card));
  box-shadow: var(--shadow);
}}
.lb-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }}
.lb-eyebrow {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }}
.lb-title {{ margin:6px 0 0; font-size:22px; font-weight:700; letter-spacing:-.02em; }}
.lb-ring {{
  width:72px; height:72px; border-radius:50%; display:grid; place-items:center; flex-shrink:0;
  background: conic-gradient(var(--accent) calc(var(--pct) * 1%), rgba(127,127,127,.15) 0);
  position:relative; font-weight:700; font-size:15px;
}}
.lb-ring::before {{
  content:""; position:absolute; inset:8px; border-radius:50%; background:var(--card);
}}
.lb-ring span {{ position:relative; }}
.lb-h1 {{ margin-top:14px; }}
.lb-h1-meta {{ display:flex; justify-content:space-between; font-size:12px; color:var(--muted); margin-bottom:6px; }}
.lb-bar {{ height:8px; border-radius:999px; background:rgba(127,127,127,.15); overflow:hidden; }}
.lb-fill {{ height:100%; background:linear-gradient(90deg,var(--accent),#30b0c7); transition:width .5s; }}
.lb-detail {{ margin:8px 0 0; font-size:13px; color:var(--muted); }}
.lb-ms {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }}
.lb-ms span {{
  font-size:12px; padding:6px 10px; border-radius:999px; background:rgba(127,127,127,.1);
}}
.lb-ms span.done {{ background:rgba(52,199,89,.14); color:var(--ok); font-weight:600; }}
.lb-block {{ margin:10px 0 0; font-size:13px; color:var(--warn); }}
.lb-updated {{ margin:10px 0 0; font-size:11px; color:var(--muted); }}
.preview-embed .top .brand::after {{ content:" · Preview"; color:var(--muted); font-weight:500; }}
"""

LAUNCH_EMBED_JS = """
async function refreshLaunchBoard() {
  try {
    const r = await fetch('/api/launch/status', { cache: 'no-store' });
    const d = await r.json();
    const h1 = d.h1 || {};
    const overall = d.overall_pct || 0;
    const h1pct = h1.progress_pct || 0;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('lb-headline', d.headline_de || '');
    set('lb-overall', overall + '%');
    set('lb-h1-status', h1.status || '—');
    set('lb-h1-pct', h1pct + '%');
    set('lb-h1-detail', h1.detail_de || '');
    set('lb-updated', d.updated_at_utc || '');
    const ring = document.getElementById('lb-ring');
    if (ring) ring.style.setProperty('--pct', overall);
    const fill = document.getElementById('lb-h1-fill');
    if (fill) fill.style.width = h1pct + '%';
    const ms = document.getElementById('lb-milestones');
    if (ms && Array.isArray(d.milestones)) {
      ms.innerHTML = d.milestones.map(m =>
        '<span class="' + (m.done ? 'done' : '') + '">' + (m.label_de || '') + '</span>'
      ).join('');
    }
    const lt = document.getElementById('lb-tiles');
    if (lt && Array.isArray(d.tiles)) {
      lt.innerHTML = d.tiles.map(t => {
        const cls = t.ok ? 'ok' : '';
        return '<div class="lb-tile ' + cls + '">' +
          '<div class="lb-tile-label">' + (t.label_de || '') + '</div>' +
          '<div class="lb-tile-value">' + (t.value_de || '') + '</div>' +
          '<div class="lb-tile-detail">' + (t.detail_de || '') + '</div></div>';
      }).join('');
    }
  } catch (e) {}
}
setInterval(refreshLaunchBoard, 12000);
"""


def embed_launch_into_preview(preview_html: str, launch_doc: Dict[str, Any]) -> str:
    """Preview-HTML mit Weltneuheit-Hero und Navigation anreichern (nur mit KI-Kernel)."""
    root = Path(__file__).resolve().parents[1]
    try:
        from analytics.r3_launch_world import (
            render_kernel_gate_section,
            render_world_launch_section,
            world_launch_kernel_gate,
        )

        gate = launch_doc.get("kernel_gate") or world_launch_kernel_gate(root)
        if gate.get("allowed"):
            strip = render_world_launch_section(launch_doc, root)
        else:
            strip = render_kernel_gate_section(gate, root)
    except Exception:
        strip = render_launch_embed_strip(launch_doc)
    from analytics.r3_surface_theme import render_nav

    nav = render_nav(root, active="home")

    html_out = preview_html
    from analytics.r3_surface_theme import surface_title

    html_out = html_out.replace(
        "<title>R3 · Cockpit</title>",
        f"<title>{html.escape(surface_title(root))}</title>",
        1,
    )
    try:
        from analytics.r3_launch_world import WORLD_LAUNCH_CSS, WORLD_LAUNCH_JS

        extra_css = WORLD_LAUNCH_CSS
        extra_js = WORLD_LAUNCH_JS
    except Exception:
        extra_css = LAUNCH_EMBED_CSS
        extra_js = LAUNCH_EMBED_JS
    html_out = html_out.replace("</style>", LAUNCH_EMBED_CSS + extra_css + SYSTEM_STATUS_CSS + "</style>", 1)

    body_idx = html_out.find("<body>")
    if body_idx >= 0:
        insert = html_out.find(">", body_idx) + 1
        html_out = (
            html_out[:insert]
            + nav
            + strip
            + '<div class="preview-embed">'
            + html_out[insert:]
        )
        from analytics.preview_status_visual import SYSTEM_STATUS_JS

        storage_key = "r3_world_launch_seen_v1"
        try:
            from analytics.r3_launch_world import load_launch_world

            storage_key = str(load_launch_world(root).get("storage_key") or storage_key)
        except Exception:
            pass
        html_out = html_out.replace("<body>", f'<body data-reveal-key="{html.escape(storage_key)}">', 1)
        html_out = html_out.replace("</body>", extra_js + SYSTEM_STATUS_JS + "</div></body>", 1)

    return html_out
