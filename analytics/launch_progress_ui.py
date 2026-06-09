"""Launch-Fortschritt UI — Apple-inspiriert für Ubuntu."""
from __future__ import annotations

import html
import json
from typing import Any, Dict


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _tile_html(tile: Dict[str, Any]) -> str:
    ok = bool(tile.get("ok"))
    cls = "tile ok" if ok else "tile"
    return f"""
    <div class="{cls}">
      <div class="tile-label">{_esc(tile.get('label_de'))}</div>
      <div class="tile-value">{_esc(tile.get('value_de'))}</div>
      <div class="tile-detail">{_esc(tile.get('detail_de'))}</div>
    </div>"""


def _milestone_html(ms: Dict[str, Any]) -> str:
    done = bool(ms.get("done"))
    cls = "ms done" if done else "ms"
    mark = "✓" if done else "○"
    return f'<div class="{cls}"><span class="ms-mark">{mark}</span><span>{_esc(ms.get("label_de"))}</span></div>'


def render_launch_progress_page(doc: Dict[str, Any]) -> bytes:
    overall = int(doc.get("overall_pct") or 0)
    h1_pct = int((doc.get("h1") or {}).get("progress_pct") or 0)
    headline = str(doc.get("headline_de") or "Launch-Fortschritt")
    updated = str(doc.get("updated_at_utc") or "")
    public_url = str((doc.get("remote") or {}).get("public_base_url") or "")
    join_url = str(doc.get("join_url") or "")
    blockers = doc.get("blockers_de") or []
    h1_doc = doc.get("h1") or {}
    h1_detail = str(h1_doc.get("detail_de") or "")
    h1_status = str(h1_doc.get("status") or "—")

    tiles = "".join(_tile_html(t) for t in (doc.get("tiles") or []))
    milestones = "".join(_milestone_html(m) for m in (doc.get("milestones") or []))
    blocker_html = ""
    if blockers:
        items = "".join(f"<li>{_esc(b)}</li>" for b in blockers)
        blocker_html = f'<div class="blockers"><div class="blockers-title">Offen</div><ul>{items}</ul></div>'

    preview_url = str(doc.get("preview_url") or doc.get("hub_url") or "/")
    link_row = f"""
        <div class="links">
          <a class="pill" href="{_esc(preview_url)}">Command Center</a>
          <a class="pill secondary" href="/legion">Legion</a>
          <a class="pill secondary" href="/join">Join</a>"""
    if public_url:
        link_row += f"""
          <a class="pill secondary" href="{_esc(public_url)}" target="_blank" rel="noopener">Remote</a>"""
    link_row += "\n        </div>"

    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Active Alpha — Launch</title>
<style>
:root {{
  --bg: #f5f5f7;
  --card: rgba(255,255,255,0.86);
  --text: #1d1d1f;
  --muted: #6e6e73;
  --line: rgba(0,0,0,0.08);
  --accent: #0071e3;
  --ok: #34c759;
  --warn: #ff9500;
  --shadow: 0 20px 60px rgba(0,0,0,0.08);
  --radius: 20px;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #000;
    --card: rgba(28,28,30,0.88);
    --text: #f5f5f7;
    --muted: #a1a1a6;
    --line: rgba(255,255,255,0.12);
    --shadow: 0 20px 60px rgba(0,0,0,0.45);
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; min-height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", system-ui, sans-serif;
  background: radial-gradient(ellipse at top, #fff 0%, var(--bg) 58%);
  color: var(--text);
  -webkit-font-smoothing: antialiased;
}}
@media (prefers-color-scheme: dark) {{
  body {{ background: radial-gradient(ellipse at top, #1c1c1e 0%, #000 62%); }}
}}
.wrap {{ max-width: 720px; margin: 0 auto; padding: 40px 20px 28px; }}
.nav {{ display:flex; justify-content:center; gap:8px; margin-bottom: 18px; }}
.nav a {{
  padding:8px 14px; border-radius:999px; text-decoration:none; font-size:13px; font-weight:600;
  background: var(--accent); color:#fff;
}}
.nav a.secondary {{ background: rgba(127,127,127,0.12); color: var(--text); }}
.hero {{ text-align: center; margin-bottom: 24px; }}
.eyebrow {{ font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }}
h1 {{ margin: 8px 0 6px; font-size: 30px; font-weight: 600; letter-spacing: -0.02em; }}
.sub {{ color: var(--muted); font-size: 15px; margin: 0; }}
.ring-wrap {{ display: grid; place-items: center; margin: 22px 0 8px; }}
.ring {{
  width: 168px; height: 168px; border-radius: 50%;
  background: conic-gradient(var(--accent) {overall}%, rgba(127,127,127,0.15) 0);
  display: grid; place-items: center; position: relative;
}}
.ring::before {{
  content: ""; position: absolute; inset: 14px; border-radius: 50%; background: var(--bg);
}}
.ring-inner {{ position: relative; text-align: center; }}
.ring-pct {{ font-size: 36px; font-weight: 700; letter-spacing: -0.03em; }}
.ring-cap {{ font-size: 12px; color: var(--muted); }}
.card {{
  backdrop-filter: saturate(180%) blur(20px);
  background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px; margin-bottom: 14px;
}}
.section-title {{ font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin-bottom: 12px; }}
.h1-bar {{ height: 10px; border-radius: 999px; background: rgba(127,127,127,0.15); overflow: hidden; }}
.h1-fill {{ height: 100%; width: {h1_pct}%; background: linear-gradient(90deg, var(--accent), #30b0c7); transition: width .6s ease; }}
.h1-meta {{ display:flex; justify-content:space-between; margin-top:8px; font-size:13px; color:var(--muted); }}
.tiles {{ display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:10px; }}
@media (max-width: 560px) {{ .tiles {{ grid-template-columns: 1fr; }} }}
.tile {{ padding: 12px; border-radius: 14px; background: rgba(127,127,127,0.06); border: 1px solid var(--line); }}
.tile.ok {{ border-color: rgba(52,199,89,0.35); background: rgba(52,199,89,0.08); }}
.tile-label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }}
.tile-value {{ font-size: 18px; font-weight: 600; margin-top: 4px; }}
.tile-detail {{ font-size: 11px; color: var(--muted); margin-top: 4px; word-break: break-all; }}
.ms-wrap {{ display:flex; flex-wrap:wrap; gap:8px; }}
.ms {{ display:flex; align-items:center; gap:6px; padding:8px 12px; border-radius:999px; background:rgba(127,127,127,0.08); font-size:13px; }}
.ms.done {{ background: rgba(52,199,89,0.12); color: var(--ok); }}
.ms-mark {{ font-weight:700; }}
.blockers {{ margin-top: 12px; padding: 12px; border-radius: 12px; background: rgba(255,149,0,0.1); }}
.blockers-title {{ font-size: 12px; font-weight: 600; color: var(--warn); margin-bottom: 6px; }}
.blockers ul {{ margin: 0; padding-left: 18px; font-size: 13px; color: var(--text); }}
.links {{ display:flex; flex-wrap:wrap; gap:8px; margin-top: 14px; }}
.pill {{
  display:inline-block; padding:10px 16px; border-radius:999px; text-decoration:none;
  background: var(--accent); color:#fff; font-size:13px; font-weight:600;
}}
.pill.secondary {{ background: rgba(127,127,127,0.15); color: var(--text); }}
.foot {{ text-align:center; font-size:11px; color:var(--muted); margin-top:18px; line-height:1.5; }}
</style>
</head>
<body>
<div class="wrap">
  <nav class="nav" aria-label="Hub">
    <a href="/launch">Fortschritt</a>
    <a class="secondary" href="/">Preview</a>
    <a class="secondary" href="/join">Worker</a>
  </nav>
  <div class="hero">
    <div class="eyebrow">Active Alpha · Ubuntu</div>
    <h1>Launch-Fortschritt</h1>
    <p class="sub" id="headline">{_esc(headline)}</p>
  </div>
  <div class="ring-wrap">
    <div class="ring" id="ring" style="background:conic-gradient(var(--accent) {overall}%, rgba(127,127,127,0.15) 0)">
      <div class="ring-inner">
        <div class="ring-pct" id="overall-pct">{overall}%</div>
        <div class="ring-cap">gesamt</div>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="section-title">H1 Backtest</div>
    <div class="h1-bar"><div class="h1-fill" id="h1-fill" style="width:{h1_pct}%"></div></div>
    <div class="h1-meta"><span id="h1-status">{_esc(h1_status)}</span><span id="h1-pct">{h1_pct}%</span></div>
    <p class="sub" id="h1-detail" style="margin-top:10px;text-align:left">{_esc(h1_detail)}</p>
    {blocker_html}
  </div>
  <div class="card">
    <div class="section-title">System</div>
    <div class="tiles" id="tiles">{tiles}</div>
    {link_row}
  </div>
  <div class="card">
    <div class="section-title">Meilensteine</div>
    <div class="ms-wrap" id="milestones">{milestones}</div>
  </div>
  <p class="foot">Aktualisiert: <span id="updated">{_esc(updated)}</span> · auto alle 8s<br>Hub :17890 · Nur lokal</p>
</div>
<script>
async function refresh() {{
  try {{
    const r = await fetch('/api/launch/status', {{ cache: 'no-store' }});
    const d = await r.json();
    const overall = d.overall_pct || 0;
    const h1 = d.h1 || {{}};
    const h1pct = h1.progress_pct || 0;
    document.getElementById('overall-pct').textContent = overall + '%';
    document.getElementById('ring').style.background = 'conic-gradient(var(--accent) ' + overall + '%, rgba(127,127,127,0.15) 0)';
    document.getElementById('headline').textContent = d.headline_de || '';
    document.getElementById('h1-fill').style.width = h1pct + '%';
    document.getElementById('h1-pct').textContent = h1pct + '%';
    document.getElementById('h1-status').textContent = h1.status || '—';
    document.getElementById('h1-detail').textContent = h1.detail_de || '';
    document.getElementById('updated').textContent = d.updated_at_utc || '';
  }} catch (e) {{}}
}}
setInterval(refresh, 8000);
</script>
</body>
</html>"""
    return page.encode("utf-8")
