"""R3 Shell — gemeinsame Markenfarben (Ladeschirm, CSS, Desktop-Icon, Favicon)."""
from __future__ import annotations

from pathlib import Path

R3_APP_NAME = "R3"
R3_ORANGE_TOP = "#ff6b35"
R3_ORANGE_BOTTOM = "#e95420"
R3_ORANGE_TEXT = "#e95420"
R3_BRAND_GRADIENT = f"linear-gradient(145deg, {R3_ORANGE_TOP} 0%, {R3_ORANGE_BOTTOM} 100%)"
R3_BRAND_SHADOW = "0 4px 16px rgba(233,84,32,.25)"
_ICON_REL = Path("assets/r3-os-icon.svg")


def icon_path(root: Path) -> Path:
    return Path(root) / _ICON_REL


def head_link_tags() -> str:
    """Favicon + Miniatur (Browser-Tab, Lesezeichen, Task-Vorschau)."""
    return (
        '<link rel="icon" type="image/svg+xml" href="/assets/r3-icon.svg"/>'
        '<link rel="apple-touch-icon" href="/assets/r3-icon.svg"/>'
        '<meta name="application-name" content="R3"/>'
        '<meta name="theme-color" content="#e95420"/>'
    )


def design_tokens_css() -> str:
    """Einheitliches Farbschema und Abstände für /r3."""
    return f"""
:root {{
  --r3-orange: {R3_ORANGE_TEXT};
  --r3-orange-top: {R3_ORANGE_TOP};
  --r3-orange-bottom: {R3_ORANGE_BOTTOM};
  --r3-orange-bg: rgba(233,84,32,.08);
  --r3-orange-border: rgba(233,84,32,.24);
  --r3-text: #1d1d1f;
  --r3-muted: #86868b;
  --r3-bg: #f5f5f7;
  --r3-surface: #ffffff;
  --r3-border: rgba(0,0,0,.08);
  --r3-radius: 12px;
  --r3-radius-sm: 10px;
  --r3-gap: 12px;
  --r3-pad: 12px;
  --r3-pad-lg: 16px;
  --r3-pad-x: 20px;
  --r3-ok: #248a3d;
  --r3-ok-bg: #e8f8ec;
  --r3-warn: #9a7b00;
  --r3-warn-bg: #fff8e6;
  --r3-fail: #ff3b30;
  --r3-fail-bg: #ffeceb;
  --bg: var(--r3-bg);
  --text: var(--r3-text);
  --muted: var(--r3-muted);
  --line: var(--r3-border);
}}
"""


def brand_mark_svg_inline(*, size: int = 48) -> str:
    """Inline-SVG für scharfe Darstellung (kein Raster-Scale)."""
    s = max(24, int(size))
    r = max(6, int(s * 0.22))
    fs = max(12, int(s * 0.38))
    y = int(s * 0.62)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" '
        f'viewBox="0 0 {s} {s}" role="img" aria-label="R3">'
        f'<defs><linearGradient id="r3g" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{R3_ORANGE_TOP}"/>'
        f'<stop offset="100%" stop-color="{R3_ORANGE_BOTTOM}"/>'
        f"</linearGradient></defs>"
        f'<rect width="{s}" height="{s}" rx="{r}" fill="url(#r3g)"/>'
        f'<text x="{s // 2}" y="{y}" text-anchor="middle" '
        f'font-family="system-ui,-apple-system,sans-serif" font-size="{fs}" '
        f'font-weight="700" fill="#ffffff">R3</text></svg>'
    )


def loading_html(*, title: str = "", subtitle: str = "") -> str:
    """Qt-Ladeschirm — nur Marke + Spinner."""
    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"/>
<style>
  html,body{{width:100%;height:100%;margin:0;background:#f5f5f7;
    display:grid;place-items:center;-webkit-font-smoothing:antialiased}}
  .mark{{width:64px;height:64px;border-radius:16px;
    background:{R3_BRAND_GRADIENT};color:#fff;
    display:grid;place-items:center;font-weight:700;font-size:20px;
    box-shadow:{R3_BRAND_SHADOW}}}
  .spin{{width:28px;height:28px;border:3px solid rgba(0,0,0,.08);
    border-top-color:{R3_ORANGE_TEXT};border-radius:50%;margin:20px auto 0;
    animation:r3s .85s linear infinite}}
  @keyframes r3s{{to{{transform:rotate(360deg)}}}}
</style></head><body><div class="mark">R3</div><div class="spin"></div></body></html>"""
