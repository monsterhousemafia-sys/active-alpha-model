"""R3 Oberflächen-Identität — keine Linux-Legacy-Sprache in der UI."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_IDENTITY_REL = Path("control/r3_surface_identity.json")

# Neues visuelles System — nicht Apple-Blue-Klon
R3_CSS_ROOT = """
:root {
  --bg: #0a0a0f;
  --bg-mesh: radial-gradient(1200px 600px at 10% -10%, rgba(94,92,230,.22), transparent 55%),
             radial-gradient(900px 500px at 90% 0%, rgba(48,213,200,.12), transparent 50%),
             #0a0a0f;
  --card: rgba(22,22,32,.82);
  --card-elevated: rgba(32,32,48,.9);
  --text: #f4f4f8;
  --muted: #9b9bb0;
  --line: rgba(255,255,255,.08);
  --accent: #5e5ce6;
  --accent-soft: rgba(94,92,230,.18);
  --accent-2: #30d5c8;
  --ok: #32d74b;
  --warn: #ffd60a;
  --fail: #ff453a;
  --shadow: 0 24px 80px rgba(0,0,0,.45);
  --radius: 24px;
  --font: "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f2f2f7;
    --bg-mesh: radial-gradient(1200px 600px at 10% -10%, rgba(94,92,230,.12), transparent 55%),
               radial-gradient(900px 500px at 90% 0%, rgba(48,213,200,.08), transparent 50%),
               #f2f2f7;
    --card: rgba(255,255,255,.88);
    --card-elevated: rgba(255,255,255,.95);
    --text: #1c1c1e;
    --muted: #6e6e73;
    --line: rgba(0,0,0,.06);
    --shadow: 0 24px 60px rgba(0,0,0,.08);
  }
}
body {
  background: var(--bg-mesh) !important;
  min-height: 100vh;
}
.r3-mark {
  display: inline-flex; align-items: center; gap: 10px;
  font-weight: 800; font-size: 15px; letter-spacing: .12em;
}
.r3-mark::before {
  content: "";
  width: 28px; height: 28px; border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  box-shadow: 0 8px 24px rgba(94,92,230,.35);
}
.r3-chip {
  font-size: 11px; padding: 6px 12px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent);
  border: 1px solid rgba(94,92,230,.25); font-weight: 700;
}
.r3-nav a {
  padding: 9px 16px; border-radius: 999px; text-decoration: none;
  font-size: 13px; font-weight: 600; color: var(--text);
  background: rgba(127,127,127,.1); transition: transform .15s, background .15s;
}
.r3-nav a:hover { transform: translateY(-1px); }
.r3-nav a.active {
  background: linear-gradient(135deg, var(--accent), #7d7aff);
  color: #fff; box-shadow: 0 10px 30px rgba(94,92,230,.35);
}
.r3-nav { display: flex; justify-content: center; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.r3-hero-glow {
  position: relative; overflow: hidden;
}
.r3-hero-glow::after {
  content: ""; position: absolute; inset: -40% -20% auto -20%; height: 120px;
  background: radial-gradient(ellipse, rgba(94,92,230,.25), transparent 70%);
  pointer-events: none;
}
"""


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_surface_identity(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _IDENTITY_REL)
    if doc:
        return doc
    return {
        "product": "Alpha Model",
        "tagline_de": "Quantitatives Entscheidungs-Cockpit — ein Kern, ein Pfad.",
        "surface_name_de": "Cockpit",
    }


def product_name(root: Path) -> str:
    return str(load_surface_identity(root).get("product") or "Alpha Model")


def surface_title(root: Path) -> str:
    ident = load_surface_identity(root)
    return f"{ident.get('product', 'Alpha Model')} · {ident.get('surface_name_de', 'Cockpit')}"


def sanitize_surface_text(text: str) -> str:
    """Linux/Legacy-Begriffe aus sichtbarem Text entfernen."""
    if not text:
        return ""
    out = str(text)
    replacements = [
        (r"\bUbuntu\b", ""),
        (r"\bLinux\b", ""),
        (r"\bsystemd\b", ""),
        (r"Command Center", "Cockpit"),
        (r"Active Alpha", "Alpha Model"),
        (r"\bR3\b", "Alpha Model"),
        (r"Cursor nicht erreichbar[^—]*", "R3 KI lokal"),
        (r"Cursor-Interface[^—]*", "Bau-Werkzeug"),
        (r"Grundlage des neuen Kernels", "Bau-Werkzeug — nicht der R3-Kern"),
        (r"Cognitive Kernel v2\b", "R3 Kern"),
        (r"Cognitive Kernel\b", "R3 Kern"),
        (r"\baa_scheduler\b", "Scheduler"),
        (r"Preview Hub", "Cockpit"),
        (r"ai_kernel", ""),
        (r"Legacy[- ]?", ""),
        (r"Lean-Modus", "Fokus"),
        (r"H1 Backtest", "Validierung"),
        (r"\bH1\b", "Validierung"),
        (r"Der einzig wahre Steuerungskernel — Cursor-Interface, aa_scheduler, Preview Hub\.?",
         "R3 Kern steuert alles — Verbindung, Scheduler und Cockpit."),
    ]
    for pat, repl in replacements:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r" — —", " —", out)
    return out.strip(" ·—")


def friendly_tile(tile: Dict[str, Any], root: Path) -> Dict[str, Any]:
    ident = load_surface_identity(root)
    labels = ident.get("tile_labels") or {}
    tid = str(tile.get("id") or "")
    meta = labels.get(tid) or {}
    t = dict(tile)
    if meta.get("label_de"):
        t["label_de"] = meta["label_de"]
    if meta.get("value_ok_de") and t.get("ok"):
        t["value_de"] = meta["value_ok_de"]
    if t.get("detail_de"):
        try:
            from analytics.r3_local_surface import hide_tunnel_url

            t["detail_de"] = hide_tunnel_url(sanitize_surface_text(str(t["detail_de"])))
        except Exception:
            t["detail_de"] = sanitize_surface_text(str(t["detail_de"]))
        t["detail_de"] = str(t["detail_de"])[:140]
    if t.get("value_de"):
        t["value_de"] = sanitize_surface_text(str(t["value_de"]))
    return t


def friendly_status(status: Dict[str, Any], root: Path) -> Dict[str, Any]:
    if not status:
        return status
    out = dict(status)
    if out.get("headline_de"):
        out["headline_de"] = sanitize_surface_text(str(out["headline_de"]))
    tiles = [friendly_tile(t, root) for t in (out.get("tiles") or [])]
    out["tiles"] = tiles
    blockers = [sanitize_surface_text(b) for b in (out.get("blockers_de") or []) if sanitize_surface_text(b)]
    out["blockers_de"] = blockers
    op = dict(out.get("operator") or {})
    for key in ("headline_de", "chat_next_de", "circle_headline_de", "last_action_de"):
        if op.get(key):
            op[key] = sanitize_surface_text(str(op[key]))
    out["operator"] = op
    return out


def render_nav(root: Path, *, active: str = "home") -> str:
    ident = load_surface_identity(root)
    items = ident.get("nav") or [
        {"id": "home", "label_de": "Cockpit", "href": "/"},
        {"id": "legion", "label_de": "Netzwerk", "href": "/legion"},
        {"id": "join", "label_de": "Mitmachen", "href": "/join"},
    ]
    links = []
    for item in items:
        iid = str(item.get("id") or "")
        cls = "active" if iid == active else ""
        links.append(
            f'<a class="{cls}" href="{html.escape(str(item.get("href") or "/"))}">'
            f'{html.escape(str(item.get("label_de") or ""))}</a>'
        )
    return f'<nav class="r3-nav" aria-label="R3">{"".join(links)}</nav>'


def render_page_header(root: Path, *, chip: str = "") -> str:
    ident = load_surface_identity(root)
    prod = html.escape(str(ident.get("product") or "R3"))
    tag = html.escape(str(ident.get("tagline_de") or ""))
    chip_html = f'<div class="r3-chip">{html.escape(chip)}</div>' if chip else ""
    return f"""
    <header class="r3-top">
      <div>
        <div class="r3-mark">{prod}</div>
        <p class="r3-tagline">{tag}</p>
      </div>
      {chip_html}
    </header>"""
