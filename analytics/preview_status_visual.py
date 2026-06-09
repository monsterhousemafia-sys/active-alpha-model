"""System status rendering for R3 Cockpit."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List, Optional


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _tile_html(tile: Dict[str, Any]) -> str:
    cls = str(tile.get("status_class") or ("ok" if tile.get("ok") else "warn"))
    return f"""
    <div class="st-tile {cls}" data-tile="{_esc(tile.get('id'))}">
      <div class="st-tile-label">{_esc(tile.get('label_de'))}</div>
      <div class="st-tile-value">{_esc(tile.get('value_de'))}</div>
      <div class="st-tile-detail">{_esc(tile.get('detail_de'))}</div>
    </div>"""


def _launch_tile_html(tile: Dict[str, Any]) -> str:
    cls = "ok" if tile.get("ok") else ""
    return f"""
    <div class="lb-tile {cls}">
      <div class="lb-tile-label">{_esc(tile.get('label_de'))}</div>
      <div class="lb-tile-value">{_esc(tile.get('value_de'))}</div>
      <div class="lb-tile-detail">{_esc(tile.get('detail_de'))}</div>
    </div>"""


def render_ki_console_block(status: Dict[str, Any], *, root: Optional[Path] = None) -> str:
    ki_next = dict(status.get("ki_next") or {})
    health = dict(status.get("ki_health") or {})
    if root is not None and not health:
        try:
            from analytics.r3_ki_console import ki_health

            health = ki_health(root)
        except Exception:
            health = {}
    try:
        from analytics.r3_ki_console import render_ki_console_section

        return render_ki_console_section(ki_next, health=health)
    except Exception:
        return ""


def render_system_status_section(status: Dict[str, Any], *, root: Optional[Path] = None) -> str:
    if not status:
        return ""
    if root is not None:
        try:
            from analytics.r3_surface_theme import friendly_status, load_surface_identity, product_name

            status = friendly_status(status, root)
            eyebrow = f"{product_name(root)} · {load_surface_identity(root).get('sections', {}).get('status', 'Kern-Status')}"
        except Exception:
            eyebrow = "R3 · Kern-Status"
    else:
        eyebrow = "R3 · Kern-Status"
    composite = int(status.get("composite_pct") or 0)
    tiles = "".join(_tile_html(t) for t in (status.get("tiles") or []))
    blockers = status.get("blockers_de") or []
    blocker_html = ""
    if blockers:
        blocker_html = f'<p class="st-blocker">{_esc(blockers[0])}</p>'

    op = status.get("operator") or {}
    sub = _esc(op.get("chat_next_de") or op.get("circle_headline_de") or status.get("headline_de"))

    pilot_block = ""
    try:
        from analytics.r3_pilot_central import render_pilot_central_section

        pilot_block = render_pilot_central_section(dict(status.get("pilot_board") or {}))
    except Exception:
        pilot_block = ""

    forschung_block = ""
    try:
        from analytics.r3_public import hide_trading_in_ui, render_support_section

        if root is not None and hide_trading_in_ui(root):
            forschung_block = render_support_section(root)
        else:
            from analytics.r3_forschungszweig import render_forschungszweig_section

            forschung_block = render_forschungszweig_section(dict(status.get("forschungszweig") or {}))
    except Exception:
        forschung_block = ""

    ki_block = render_ki_console_block(status, root=root)
    trail_block = ""
    try:
        from analytics.r3_dev_trail import render_dev_trail_section

        trail_block = render_dev_trail_section(dict(status.get("dev_trail") or {}))
    except Exception:
        trail_block = ""

    return f"""
<section class="system-status" id="system-status" aria-label="Systemstatus">
  <div class="st-hero">
    <div class="st-copy">
      <div class="st-eyebrow">{_esc(eyebrow)}</div>
      <h2 class="st-title" id="st-headline">{_esc(status.get('headline_de'))}</h2>
      <p class="st-sub" id="st-sub">{sub}</p>
      {blocker_html}
    </div>
    <div class="st-ring" id="st-ring" style="--pct:{composite}">
      <span id="st-composite">{composite}%</span>
    </div>
  </div>
  <div class="st-tiles" id="st-tiles">{tiles}</div>
  <p class="st-updated">Live · <span id="st-updated">{_esc(status.get('updated_at_utc'))}</span></p>
</section>
{pilot_block}
{forschung_block}
{ki_block}
{trail_block}"""


def render_launch_tiles_row(tiles: List[Dict[str, Any]]) -> str:
    if not tiles:
        return ""
    inner = "".join(_launch_tile_html(t) for t in tiles)
    return f'<div class="lb-tiles" id="lb-tiles">{inner}</div>'


SYSTEM_STATUS_CSS = """
.system-status {{
  margin-bottom: 22px; padding: 22px 24px; border-radius: var(--radius, 24px);
  border: 1px solid rgba(94,92,230,.22);
  background: linear-gradient(165deg, rgba(94,92,230,.12) 0%, var(--card) 52%);
  box-shadow: var(--shadow);
}}
.st-hero {{ display:flex; justify-content:space-between; align-items:flex-start; gap:18px; }}
.st-copy {{ flex:1; min-width:0; }}
.st-eyebrow {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }}
.st-title {{ margin:6px 0 8px; font-size:clamp(22px,4vw,28px); font-weight:700; letter-spacing:-.02em; }}
.st-sub {{ margin:0; font-size:14px; color:var(--muted); line-height:1.45; }}
.st-blocker {{ margin:10px 0 0; font-size:13px; color:var(--warn); }}
.st-ring {{
  width:88px; height:88px; border-radius:50%; flex-shrink:0;
  display:grid; place-items:center; position:relative; font-weight:700; font-size:18px;
  background: conic-gradient(var(--accent) calc(var(--pct) * 1%), rgba(127,127,127,.14) 0);
}}
.st-ring::before {{
  content:""; position:absolute; inset:9px; border-radius:50%; background:var(--card);
}}
.st-ring span {{ position:relative; }}
.st-tiles {{
  display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap:10px; margin-top:16px;
}}
@media (max-width: 720px) {{ .st-tiles {{ grid-template-columns: repeat(2, 1fr); }} }}
@media (max-width: 420px) {{ .st-tiles {{ grid-template-columns: 1fr; }} }}
.st-tile {{
  padding:12px 14px; border-radius:16px; background:rgba(0,0,0,.03);
  border:1px solid var(--line); transition: border-color .2s, background .2s;
}}
@media (prefers-color-scheme: dark) {{ .st-tile {{ background:rgba(255,255,255,.04); }} }}
.st-tile.ok {{ border-color: rgba(52,199,89,.32); }}
.st-tile.warn {{ border-color: rgba(255,159,10,.35); }}
.st-tile.fail {{ border-color: rgba(255,59,48,.35); }}
.st-tile-label {{ font-size:10px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }}
.st-tile-value {{ font-size:17px; font-weight:700; margin-top:4px; }}
.st-tile-detail {{ font-size:11px; color:var(--muted); margin-top:4px; line-height:1.35; }}
.st-updated {{ margin:12px 0 0; font-size:11px; color:var(--muted); text-align:right; }}
.lb-tiles {{
  display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap:8px; margin-top:12px;
}}
@media (max-width: 640px) {{ .lb-tiles {{ grid-template-columns: repeat(2, 1fr); }} }}
.lb-tile {{
  padding:10px 12px; border-radius:14px; background:rgba(127,127,127,.06); border:1px solid var(--line);
}}
.lb-tile.ok {{ border-color:rgba(52,199,89,.3); background:rgba(52,199,89,.07); }}
.lb-tile-label {{ font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }}
.lb-tile-value {{ font-size:15px; font-weight:600; margin-top:3px; }}
.lb-tile-detail {{ font-size:10px; color:var(--muted); margin-top:3px; word-break:break-all; }}
.pilot-central {{
  margin-bottom: 22px; padding: 20px 22px; border-radius: var(--radius, 24px);
  border: 1px solid rgba(255,159,10,.35);
  background: linear-gradient(165deg, rgba(255,159,10,.12) 0%, var(--card) 55%);
  box-shadow: var(--shadow);
}}
.pz-eyebrow {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--warn); }}
.pz-title {{ margin:6px 0 4px; font-size:clamp(22px,3.2vw,28px); font-weight:800; }}
.pz-tagline {{ margin:0 0 14px; font-size:14px; color:var(--muted); }}
.pz-current {{
  padding:14px 16px; border-radius:16px; border:1px solid var(--line);
  background:rgba(0,0,0,.03); margin-bottom:14px;
}}
.pz-current-label {{ font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); }}
.pz-mandate {{ margin:8px 0 6px; font-size:17px; font-weight:700; line-height:1.35; }}
.pz-meta {{ margin:0 0 8px; font-size:12px; color:var(--muted); }}
.pz-preview {{ margin:0; font-size:13px; color:var(--text); line-height:1.45; white-space:pre-wrap; }}
.pz-king-actions {{ display:flex; gap:10px; margin-top:12px; }}
.pz-approve,.pz-reject {{
  border:0; border-radius:12px; padding:10px 18px; font-weight:700; cursor:pointer; font-family:inherit;
}}
.pz-approve {{ background:var(--ok); color:#fff; }}
.pz-reject {{ background:rgba(255,59,48,.15); color:var(--text); }}
.pz-cols {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
.pz-col h3 {{ margin:0 0 8px; font-size:13px; }}
.pz-queue,.pz-live {{ margin:0; padding:0; list-style:none; font-size:12px; }}
.pz-queue li,.pz-live li {{ padding:6px 0; border-bottom:1px solid var(--line); }}
.pz-q-status {{ font-weight:700; margin-right:6px; }}
.pz-chat-hint {{ margin:12px 0 0; font-size:12px; color:var(--ok); }}
@media (max-width:720px) {{ .pz-cols {{ grid-template-columns:1fr; }} }}
.forschungszweig {{
  margin-bottom: 22px; padding: 20px 22px; border-radius: var(--radius, 24px);
  border: 1px solid rgba(94,92,230,.32);
  background: linear-gradient(165deg, rgba(94,92,230,.1) 0%, var(--card) 55%);
  box-shadow: var(--shadow);
}}
.fz-eyebrow {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent); }}
.fz-title {{ margin:6px 0 4px; font-size:clamp(20px,3vw,26px); font-weight:800; }}
.fz-mission,.fz-sep {{ margin:0 0 8px; font-size:13px; color:var(--muted); line-height:1.45; }}
.fz-prognosis {{ padding:12px 14px; border-radius:14px; border:1px solid var(--line); margin:12px 0; }}
.fz-prog-label {{ font-size:11px; text-transform:uppercase; color:var(--muted); }}
.fz-headline {{ margin:8px 0 4px; font-size:16px; font-weight:700; }}
.fz-detail,.fz-next,.fz-h1 {{ margin:0 0 6px; font-size:12px; color:var(--muted); }}
.fz-funding {{ font-size:12px; margin-bottom:10px; }}
.fz-tier {{ font-weight:700; margin-right:8px; color:var(--ok); }}
.fz-queue {{ margin:0; padding:0; list-style:none; font-size:12px; }}
.fz-queue li {{ padding:5px 0; border-bottom:1px solid var(--line); }}
.fz-cmds {{ margin:10px 0 0; font-size:11px; color:var(--muted); }}
.fz-geheimnis {{ margin:10px 0 0; padding:10px; border-radius:10px; background:rgba(94,92,230,.08); font-size:12px; white-space:pre-wrap; line-height:1.4; }}
.fz-geheimnis-hint {{ margin:6px 0 0; font-size:11px; color:var(--accent); }}
.fz-public .fz-ways {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin:12px 0; }}
.fz-way {{ padding:12px; border-radius:14px; border:1px solid var(--line); background:rgba(94,92,230,.05); font-size:12px; }}
.fz-way p {{ margin:6px 0; color:var(--muted); line-height:1.4; }}
.fz-way code {{ font-size:11px; color:var(--accent); }}
.fz-donate-row {{ display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-top:8px; }}
.fz-donate-btn {{
  border:0; border-radius:999px; padding:10px 18px; font-weight:700; cursor:pointer;
  background:linear-gradient(135deg,var(--accent),#7d7aff); color:#fff; font-family:inherit;
  text-decoration:none; font-size:13px;
}}
.fz-donate-note {{ font-size:12px; color:var(--muted); }}
.dev-trail {{
  margin-bottom: 22px; padding: 20px 22px; border-radius: var(--radius, 24px);
  border: 1px solid rgba(48,213,200,.22);
  background: linear-gradient(165deg, rgba(48,213,200,.08) 0%, var(--card) 58%);
  box-shadow: var(--shadow);
}}
.dt-eyebrow {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }}
.dt-title {{ margin:6px 0 4px; font-size:clamp(20px,3vw,24px); font-weight:700; }}
.dt-mission {{ margin:0 0 8px; font-size:14px; color:var(--muted); line-height:1.45; }}
.dt-continuity {{ margin:0 0 14px; font-size:13px; color:var(--ok); font-weight:600; }}
.kernel-roles {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:0 0 16px; }}
.kr-col {{ border:1px solid var(--border); border-radius:12px; padding:12px 14px; background:rgba(255,255,255,.02); }}
.kr-eyebrow {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin-bottom:6px; }}
.kr-def,.kr-role {{ margin:0 0 8px; font-size:13px; line-height:1.45; }}
.kr-not {{ margin:0 0 6px; font-size:12px; color:var(--muted); }}
.kr-status {{ margin:0; font-size:12px; color:var(--ok); font-weight:600; }}
.kr-comps {{ display:flex; flex-direction:column; gap:8px; margin-top:8px; }}
.kr-comp {{ display:flex; gap:8px; font-size:12px; }}
.kr-comp p {{ margin:2px 0 0; color:var(--muted); }}
.kr-mark {{ color:var(--ok); font-weight:700; }}
.kr-comp.kr-warn .kr-mark {{ color:var(--warn); }}
.kr-cursor-active {{ border-color:rgba(120,180,255,.35); }}
@media (max-width:720px) {{ .kernel-roles {{ grid-template-columns:1fr; }} }}
.r3-build {{ margin:0 0 16px; border:1px solid var(--border); border-radius:12px; padding:12px 14px; background:rgba(90,140,255,.04); }}
.rb-eyebrow {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }}
.rb-title {{ margin:4px 0 6px; font-size:16px; }}
.rb-meta,.rb-hint {{ margin:0 0 6px; font-size:12px; color:var(--muted); line-height:1.45; }}
.rb-cmds {{ margin:8px 0 0; font-size:12px; color:var(--ok); }}
.r3-build-kernel {{ margin:0 0 16px; border:1px solid rgba(100,180,120,.35); border-radius:12px; padding:14px; background:rgba(40,90,60,.08); }}
.rbk-eyebrow {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--ok); }}
.rbk-title {{ margin:4px 0 6px; font-size:17px; }}
.rbk-meta,.rbk-replaces,.rbk-last {{ margin:0 0 6px; font-size:12px; color:var(--muted); line-height:1.45; }}
.rbk-cmd {{ margin:8px 0 0; font-size:13px; color:var(--ok); font-weight:600; }}
.dt-paths {{ display:grid; gap:10px; margin-bottom:14px; }}
.dt-path {{
  display:flex; flex-wrap:wrap; align-items:center; gap:8px;
  padding:10px 12px; border-radius:12px; background:rgba(0,0,0,.04); border:1px solid var(--line);
}}
@media (prefers-color-scheme: dark) {{ .dt-path {{ background:rgba(255,255,255,.04); }} }}
.dt-path-k {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); min-width:92px; }}
.dt-path-v {{ font-size:12px; word-break:break-all; flex:1; }}
.dt-copy {{
  border:1px solid var(--line); background:transparent; border-radius:999px;
  padding:4px 10px; font-size:11px; cursor:pointer; color:var(--muted); font-family:inherit;
}}
.dt-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
@media (max-width: 760px) {{ .dt-grid {{ grid-template-columns:1fr; }} }}
.dt-col h3 {{ margin:0 0 8px; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
.dt-next {{ margin:0; padding-left:18px; font-size:14px; line-height:1.45; }}
.dt-next li {{ margin-bottom:6px; }}
.dt-item {{ display:flex; gap:10px; margin-bottom:10px; align-items:flex-start; }}
.dt-badge {{
  font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.04em;
  padding:4px 8px; border-radius:999px; background:rgba(127,127,127,.12); flex-shrink:0;
}}
.dt-item.dt-active .dt-badge {{ background:rgba(94,92,230,.16); color:var(--accent); }}
.dt-item.dt-done .dt-badge {{ background:rgba(52,199,89,.14); color:var(--ok); }}
.dt-item p {{ margin:4px 0 0; font-size:12px; color:var(--muted); line-height:1.35; }}
.dt-note {{ margin:12px 0 0; font-size:12px; color:var(--muted); }}
"""

from analytics.r3_ki_chat_ui import KI_CHAT_CSS, KI_CHAT_JS  # noqa: E402

SYSTEM_STATUS_CSS = SYSTEM_STATUS_CSS + KI_CHAT_CSS

SYSTEM_STATUS_JS = """
async function refreshSystemStatus() {
  try {
    const r = await fetch('/api/system/status', { cache: 'no-store' });
    const d = await r.json();
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    const composite = d.composite_pct || 0;
    set('st-headline', d.headline_de || '—');
    const op = d.operator || {};
    set('st-sub', op.chat_next_de || op.circle_headline_de || d.headline_de || '');
    set('st-composite', composite + '%');
    set('st-updated', d.updated_at_utc || '');
    const ring = document.getElementById('st-ring');
    if (ring) ring.style.setProperty('--pct', composite);
    const tiles = document.getElementById('st-tiles');
    if (tiles && Array.isArray(d.tiles)) {
      tiles.innerHTML = d.tiles.map(t => {
        const cls = t.status_class || (t.ok ? 'ok' : 'warn');
        return '<div class="st-tile ' + cls + '">' +
          '<div class="st-tile-label">' + (t.label_de || '') + '</div>' +
          '<div class="st-tile-value">' + (t.value_de || '') + '</div>' +
          '<div class="st-tile-detail">' + (t.detail_de || '') + '</div></div>';
      }).join('');
    }
    const blocker = document.querySelector('.st-blocker');
    const b0 = (d.blockers_de || [])[0];
    if (blocker) blocker.textContent = b0 || '';
    else if (b0) {
      const sub = document.getElementById('st-sub');
      if (sub && !sub.textContent) sub.textContent = b0;
    }
    const ki = d.ki_next || {};
    const hint = document.getElementById('ki-next-hint');
    if (hint && ki.next_step_de) hint.textContent = ki.next_step_de;
    const kh = d.ki_health || {};
    const setKi = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    if (kh.model) setKi('ki-model', kh.model);
    if (kh.ready !== undefined) setKi('ki-status', kh.ready ? 'Bereit' : 'Setup');
    if (kh.internet_ok !== undefined) setKi('ki-internet', kh.internet_ok ? 'Netz OK' : 'Netz offline');
    if (kh.power_pct !== undefined) setKi('ki-power-pct', kh.power_pct + '%');
    const pbar = document.getElementById('ki-power-bar');
    const mods = (kh.power || {}).modules || [];
    if (pbar && mods.length) {
      const labels = { ml:'ML', ollama:'Ollama', cloud:'Cloud', build:'Bau', pilot:'Pilot', storage:'Speicher' };
      let cmdMap = {};
      try { cmdMap = JSON.parse(pbar.getAttribute('data-module-cmds') || '{}') || {}; } catch (e) {}
      pbar.innerHTML = mods.map(m => {
        const id = m.id || '';
        const cmd = cmdMap[id] || '';
        const title = cmd ? (' title="' + cmd.replace(/"/g, '') + '"') : '';
        return '<button type="button" class="ki-pmod ' + (m.ok ? 'ok' : '') + '" data-mod="' + id + '" data-cmd="' + cmd + '"' + title + '>' +
          (labels[id] || id) + '</button>';
      }).join('');
      if (typeof window.kiBindPowerModules === 'function') window.kiBindPowerModules();
    }
    const fz = d.forschungszweig || {};
    const setFz = (id, val) => { const el = document.getElementById(id); if (el && val !== undefined) el.textContent = val; };
    if (fz.headline_de) setFz('fz-headline', fz.headline_de);
    if (fz.prognosis_de) setFz('fz-detail', fz.prognosis_de);
    if (fz.next_step_de) setFz('fz-next', fz.next_step_de);
    if (fz.h1 && fz.h1.banner_de) setFz('fz-h1', 'H1: ' + fz.h1.banner_de);
    if (fz.geheimnis_de) {
      const g = document.getElementById('fz-geheimnis');
      if (g) g.textContent = fz.geheimnis_de;
    }
    document.querySelectorAll('.fz-donate-btn[data-cmd]').forEach(btn => {
      if (btn._fzBound) return;
      btn._fzBound = true;
      btn.addEventListener('click', () => {
        const cmd = btn.getAttribute('data-cmd') || '/spende';
        document.getElementById('ki-console')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        if (typeof window.kiSubmit === 'function') window.kiSubmit(cmd, {});
        else {
          const input = document.getElementById('ki-input');
          const form = document.getElementById('ki-form');
          if (input) input.value = cmd;
          if (form) form.requestSubmit();
        }
      });
    });
    const fzq = document.getElementById('fz-queue');
    if (fzq && Array.isArray(fz.research_queue)) {
      fzq.innerHTML = fz.research_queue.map(item =>
        '<li><span class="fz-status">' + (item.status || '') + '</span> ' +
        (item.mandate_de || '').slice(0, 90) + '</li>'
      ).join('') || '<li class="fz-empty">/beitrag forschung &lt;Idee&gt;</li>';
    }
    const pb = d.pilot_board || {};
    const cur = pb.current || {};
    const setPz = (id, val) => { const el = document.getElementById(id); if (el && val !== undefined) el.textContent = val; };
    if (cur.mandate_de) setPz('pz-mandate', cur.mandate_de);
    if (cur.status) setPz('pz-status', cur.status);
    if (cur.preview_de) setPz('pz-preview', cur.preview_de);
    const q = document.getElementById('pz-queue');
    if (q && Array.isArray(pb.queue)) {
      q.innerHTML = pb.queue.filter(x => x.id !== cur.id).map(item =>
        '<li><span class="pz-q-status">' + (item.status || '') + '</span> ' +
        (item.author_de || '') + ' ' + (item.mandate_de || '').slice(0, 100) + '</li>'
      ).join('') || '<li class="pz-empty">—</li>';
    }
    const live = document.getElementById('pz-live');
    if (live && Array.isArray(pb.live_recent)) {
      live.innerHTML = pb.live_recent.map(item =>
        '<li>' + (item.mandate_de || '').slice(0, 90) + '</li>'
      ).join('') || '<li class="pz-empty">—</li>';
    }
    const dt = d.dev_trail || {};
    const paths = dt.paths || {};
    const setPath = (id, val) => { const el = document.getElementById(id); if (el && val) el.textContent = val; };
    setPath('dt-project-root', paths.project_root);
    setPath('dt-r3-share', paths.r3_share);
    const next = document.getElementById('dt-next');
    if (next && Array.isArray(dt.next_de)) {
      next.innerHTML = dt.next_de.map(x => '<li>' + (x || '') + '</li>').join('');
    }
    const recent = document.getElementById('dt-recent');
    if (recent && Array.isArray(dt.recent)) {
      recent.innerHTML = dt.recent.slice(0, 5).map(item => {
        const st = item.status || '';
        const badge = st === 'active' ? 'aktiv' : (st === 'done' ? 'fertig' : st);
        return '<div class="dt-item dt-' + st + '"><span class="dt-badge">' + badge + '</span><div><strong>' +
          (item.title_de || '') + '</strong><p>' + (item.detail_de || '') + '</p></div></div>';
      }).join('');
    }
  } catch (e) {}
}
(function initPilotKing() {
  async function pilotAction(action, id) {
    const r = await fetch('/api/pilot/' + action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id || '' })
    });
    const d = await r.json();
    if (d.reply_de) {
      const tr = document.getElementById('ki-transcript');
      if (tr) {
        const w = tr.querySelector('.ki-welcome');
        if (w) w.remove();
        const row = document.createElement('div');
        row.className = 'ki-row bot';
        row.innerHTML = '<div class="ki-bubble-avatar">R3</div><div class="ki-bubble">' +
          (d.reply_de || '').replace(/</g, '&lt;') + '</div>';
        tr.appendChild(row);
        tr.scrollTop = tr.scrollHeight;
      }
    }
    refreshSystemStatus();
  }
  document.querySelectorAll('[data-pilot-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      pilotAction(btn.getAttribute('data-pilot-action'), btn.getAttribute('data-id'));
    });
  });
})();
(function initDevTrailCopy() {
  document.querySelectorAll('.dt-copy').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-copy');
      const el = id ? document.getElementById(id) : null;
      if (!el) return;
      navigator.clipboard.writeText(el.textContent || '').catch(() => {});
      btn.textContent = 'OK';
      setTimeout(() => { btn.textContent = 'Kopieren'; }, 1200);
    });
  });
})();
""" + KI_CHAT_JS + """
setInterval(refreshSystemStatus, 12000);
"""
