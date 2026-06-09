"""R3 Icon-System — state-of-the-art SVG (Lucide-inspiriert, kein Emoji)."""
from __future__ import annotations

import html
import json
from typing import Dict

_S = 'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" fill="none"'


def _svg(paths: str, *, view: str = "0 0 24 24", fill_none: bool = True) -> str:
    fill = ' fill="none"' if fill_none else ""
    return f'<svg viewBox="{view}" aria-hidden="true" {_S}{fill}>{paths}</svg>'


# Shell-Kacheln + Dock (Ubuntu-Yaru-Akzent #E95420 via currentColor)
FEATURE_SVG: Dict[str, str] = {
    "files": _svg('<path d="M4 7h5l2 2h9v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7z"/><path d="M4 7V5a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v2"/>'),
    "terminal": _svg('<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 9l3 3-3 3"/><path d="M12 15h5"/>'),
    "settings": _svg('<circle cx="12" cy="12" r="3"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
    "apps": _svg('<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/>'),
    "network": _svg('<path d="M5 12a7 7 0 0 1 14 0"/><path d="M8.5 12a3.5 3.5 0 0 1 7 0"/><circle cx="12" cy="16" r="1.25" fill="currentColor" stroke="none"/>'),
    "bluetooth": _svg('<path d="M7 7l10 5-5 2.5L17 17l-10-5 5-2.5L7 7z"/>'),
    "sound": _svg('<path d="M11 5L6 9H3v6h3l5 4V5z"/><path d="M16 9a4 4 0 0 1 0 6"/><path d="M18.5 6.5a7.5 7.5 0 0 1 0 11"/>'),
    "display": _svg('<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 16v4"/>'),
    "power": _svg('<path d="M12 3v8"/><path d="M7.5 5.8A7 7 0 1 0 16.5 5.8"/>'),
    "screenshot": _svg('<rect x="3" y="6" width="18" height="14" rx="2"/><circle cx="12" cy="13" r="3.5"/><path d="M8 6l1.2-2h5.6L16 6"/>'),
    "calculator": _svg('<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8"/><path d="M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01"/>'),
    "lock": _svg('<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
    "aktien": _svg('<path d="M4 18V6"/><path d="M8 18v-5"/><path d="M12 18V9"/><path d="M16 18v-8"/><path d="M20 18V4"/>'),
    "bau": _svg('<path d="M14 3l7 7-9 9H5v-7l9-9z"/><path d="M3 21h7"/>'),
    "updates": _svg('<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>'),
    "session": _svg('<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>'),
}

UI_SVG: Dict[str, str] = {
    "mic": _svg('<path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 11a7 7 0 0 1-14 0"/><path d="M12 18v4"/><path d="M8 22h8"/>'),
    "paperclip": _svg('<path d="M8.5 14.5L14 9a3 3 0 1 0-4-4L4.5 10.5a5 5 0 1 0 7 7L17 12"/>'),
    "send": _svg('<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>'),
    "close": _svg('<path d="M18 6L6 18"/><path d="M6 6l12 12"/>'),
    "chevron-left": _svg('<path d="M15 18l-6-6 6-6"/>'),
    "folder": FEATURE_SVG["files"],
    "file": _svg('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>'),
    "package": _svg('<path d="M12 2l8 4.5v9L12 20l-8-4.5v-9L12 2z"/><path d="M12 22V11"/><path d="M20 6.5L12 11 4 6.5"/>'),
    "volume": FEATURE_SVG["sound"],
    "volume-off": _svg('<path d="M11 5L6 9H3v6h3l5 4V5z"/><path d="M22 9l-6 6"/><path d="M16 9l6 6"/>'),
    "check": _svg('<path d="M20 6L9 17l-5-5"/>'),
    "circle": _svg('<circle cx="12" cy="12" r="9"/>'),
    "partial": _svg('<circle cx="12" cy="12" r="9"/><path d="M12 3v9l6 3"/>'),
    "search": _svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/>'),
    "plus": _svg('<path d="M12 5v14"/><path d="M5 12h14"/>'),
    "download": _svg('<path d="M12 3v12"/><path d="M8 11l4 4 4-4"/><path d="M4 21h16"/>'),
    "refresh": _svg('<path d="M21 12a9 9 0 0 0-15-6"/><path d="M3 12a9 9 0 0 0 15 6"/><path d="M3 3v6h6"/><path d="M21 21v-6h-6"/>'),
    "users": _svg('<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6"/><path d="M14 20c0-2.5 1.5-4.5 4-4.5"/>'),
    "layout": _svg('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>'),
    "sparkle": _svg('<path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3z"/>'),
    "logout": _svg('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>'),
    "kernel": _svg('<path d="M12 2l2 4h4l-3 3 1 5-4-2-4 2 1-5-3-3h4l2-4z"/>'),
    "transparent": _svg('<circle cx="12" cy="12" r="9"/><path d="M12 8v8"/><path d="M8 12h8"/>'),
    "collective": _svg('<circle cx="12" cy="12" r="3"/><circle cx="5" cy="8" r="2"/><circle cx="19" cy="8" r="2"/><circle cx="5" cy="16" r="2"/><circle cx="19" cy="16" r="2"/>'),
    "step-b": _svg('<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>'),
    "minimize": _svg('<path d="M5 12h14"/>'),
    "maximize": _svg('<rect x="5" y="5" width="14" height="14" rx="2"/>'),
    "snap-left": _svg('<rect x="3" y="3" width="9" height="18" rx="1"/><rect x="14" y="3" width="7" height="18" rx="1" opacity=".35"/>'),
    "snap-right": _svg('<rect x="14" y="3" width="7" height="18" rx="1"/><rect x="3" y="3" width="9" height="18" rx="1" opacity=".35"/>'),
}

ALL_ICONS: Dict[str, str] = {**FEATURE_SVG, **UI_SVG}

ICON_ACCENT = "#E95420"

R3_ICON_CSS = """
.r3-ico {
  display: inline-flex; align-items: center; justify-content: center;
  flex-shrink: 0; line-height: 0; color: inherit;
}
.r3-ico svg { width: 1.15em; height: 1.15em; display: block; }
.r3-ico--sm svg { width: 14px; height: 14px; }
.r3-ico--md svg { width: 18px; height: 18px; }
.r3-ico--lg svg { width: 22px; height: 22px; }
.r3-ico--btn { width: 36px; height: 36px; border-radius: 50%; }
.ki-rail-icon, .ki-icon-btn .r3-ico, .ki-send-btn .r3-ico { color: inherit; }
.ki-rail-icon { width: 18px; height: 18px; }
.ki-rail-icon svg { width: 18px; height: 18px; }
.r3-closure-ico .r3-ico svg { width: 14px; height: 14px; }
.r3-native-row-ico { width: 20px; color: #E95420; }
.r3-plane-btn .r3-ico { margin-right: 4px; }
"""


def icon_svg(name: str) -> str:
    return ALL_ICONS.get(str(name or ""), ALL_ICONS["apps"])


def shell_icon_svg(feature_id: str) -> str:
    return icon_svg(feature_id)


def icon_span(name: str, *, cls: str = "r3-ico") -> str:
    extra = f" {cls}" if cls and cls != "r3-ico" else ""
    return f'<span class="r3-ico{extra}" aria-hidden="true">{icon_svg(name)}</span>'


def closure_status_icon(status: str) -> str:
    mapping = {
        "native": "check",
        "partial": "partial",
        "delegated": "circle",
        "step_b": "step-b",
        "missing": "circle",
    }
    return icon_span(mapping.get(str(status), "circle"), cls="r3-ico r3-ico--sm")


def icons_for_js() -> Dict[str, str]:
    """Kompakte Map für Client-Rendering (ohne HTML-Wrapper)."""
    return dict(ALL_ICONS)


def render_icons_js() -> str:
    """Idempotent — KI-Chat und Shell binden beide Icons ein."""
    payload = json.dumps(icons_for_js(), ensure_ascii=False)
    return f"""
window.R3_ICON_MAP = Object.assign(window.R3_ICON_MAP || {{}}, {payload});
if (!window._r3IconsReady) {{
  window._r3IconsReady = true;
  window.r3Icon = function(name) {{
    const d = document.createElement('div');
    d.innerHTML = window.R3_ICON_MAP[name] || window.R3_ICON_MAP.apps || '';
    return d.firstChild;
  }};
  window.r3IconHtml = function(name, cls) {{
    const n = window.r3Icon(name);
    if (!n) return '';
    const w = document.createElement('span');
    w.className = cls || 'r3-ico';
    w.setAttribute('aria-hidden', 'true');
    w.appendChild(n);
    return w.outerHTML;
  }};
}}
"""
