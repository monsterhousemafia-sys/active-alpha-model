"""R3 KI Chat — Cockpit-Layout: Session-Rail, verkabelte Aktionen (ohne Cursor)."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List

_CONFIG_REL = Path("control/r3_ki_chat_layout.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_chat_layout(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {}


def quick_chips(root: Path, *, public_ui: bool) -> List[Dict[str, Any]]:
    cfg = load_chat_layout(root)
    key = "quick_chips_public" if public_ui else "quick_chips_operator"
    return list(cfg.get(key) or [])


def power_module_cmds(root: Path) -> Dict[str, str]:
    cfg = load_chat_layout(root)
    raw = cfg.get("power_module_cmds") or {}
    return {str(k): str(v) for k, v in raw.items() if v}


def session_rail(root: Path) -> List[Dict[str, Any]]:
    return list(load_chat_layout(root).get("session_rail") or [])


def render_session_rail_html(root: Path) -> str:
    from analytics.r3_icons import icon_span

    esc = lambda t: html.escape(str(t or ""), quote=True)
    items = session_rail(root)
    if not items:
        return ""
    buttons: List[str] = []
    for item in items:
        bid = esc(item.get("id"))
        buttons.append(
            f'<button type="button" class="ki-rail-btn" id="ki-rail-{bid}" '
            f'data-rail-id="{bid}" '
            f'data-rail-action="{esc(item.get("action") or "")}" '
            f'data-rail-cmd="{esc(item.get("cmd") or "")}" '
            f'title="{esc(item.get("title_de") or item.get("label_de"))}" '
            f'aria-label="{esc(item.get("title_de") or item.get("label_de"))}">'
            f'<span class="ki-rail-icon" aria-hidden="true">{icon_span(str(item.get("icon") or "sparkle"))}</span>'
            f'<span class="ki-rail-label">{esc(item.get("label_de"))}</span>'
            f"</button>"
        )
    return (
        '<nav class="ki-rail" id="ki-rail" aria-label="Chat-Sitzung">'
        + "".join(buttons)
        + "</nav>"
    )


def render_quick_chips_html(root: Path, *, public_ui: bool) -> str:
    esc = lambda t: html.escape(str(t or ""), quote=True)
    chips = quick_chips(root, public_ui=public_ui)
    parts: List[str] = []
    for chip in chips:
        cmd = str(chip.get("cmd") or "")
        auto = "true" if chip.get("auto_send", True) else "false"
        parts.append(
            f'<button type="button" class="ki-chip" data-cmd="{esc(cmd)}" '
            f'data-auto-send="{auto}">{esc(chip.get("label_de") or cmd)}</button>'
        )
    return "".join(parts)


def join_reply_de(root: Path) -> str:
    root = Path(root)
    port = 17890
    try:
        from analytics.local_app_urls import local_hub_url
        from analytics.r3_local_surface import is_king_cockpit_local

        if is_king_cockpit_local(root):
            base = local_hub_url("", port=port).rstrip("/")
        else:
            from analytics.preview_federation import federation_config, hub_public_base_url

            port = int(federation_config(root).get("hub_port") or 17890)
            base = hub_public_base_url(root, port=port)
    except Exception:
        base = f"http://127.0.0.1:{port}"
    return "\n".join(
        [
            "Rechenkraft spenden — ohne Geld, als Worker:",
            "",
            f"1. Seite öffnen: {base}/join",
            f"2. Oder Download: {base}/download",
            "",
            "Du hilfst bei H1-Validation und Research-Runs — König bleibt lokal.",
            "Fragen: einfach tippen oder /fragen",
        ]
    )


def continuity_reply_de(root: Path) -> str:
    root = Path(root)
    try:
        from analytics.r3_conversation_continuity import verify_r3_chat_ready

        doc = verify_r3_chat_ready(root)
    except Exception as exc:
        return f"Kontinuitäts-Check fehlgeschlagen: {exc}"[:300]

    passed = doc.get("checks_passed")
    total = doc.get("checks_total")
    status = "bereit" if doc.get("ready_for_r3_chat") else f"{passed}/{total} Checks"
    lines = [
        str(doc.get("headline_de") or "R3 Kontinuität"),
        "",
        f"Status: {status}",
        "R3 KI lokal ist Hauptsprache — active-alpha-chat und Cockpit.",
        "Sichern: python3 tools/ai_kernel.py r3-preserve",
    ]
    return "\n".join(lines)


def migration_reply_de(root: Path) -> str:
    """Legacy-Alias."""
    return continuity_reply_de(root)


def desktop_reply_de(root: Path) -> str:
    _ = root
    return "\n".join(
        [
            "R3 System Desktop — Schritt A Oberfläche:",
            "",
            "Im Cockpit: /desktop",
            "Direkt: http://127.0.0.1:17890/desktop",
            "",
            "Fusion: Spotlight (Ctrl+K), Dock, Control Center, Native Apps.",
        ]
    )
