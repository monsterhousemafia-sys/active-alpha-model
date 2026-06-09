"""R3 König — lokale Oberfläche ohne Tunnel-in-Tunnel."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_TUNNEL_HOST_RE = re.compile(r"https?://[a-z0-9-]+\.trycloudflare\.com", re.I)


def is_king_cockpit_local(root: Path) -> bool:
    root = Path(root)
    try:
        from analytics.preview_federation import is_federation_king

        if not is_federation_king(root):
            return False
    except Exception:
        pass
    try:
        from analytics.r3_paths import is_r3_native_session

        if is_r3_native_session():
            return True
    except Exception:
        pass
    marker = Path.home() / ".local/share/r3-os/session_supremacy.json"
    return marker.is_file()


def local_hub_base_url(*, port: int = 17890) -> str:
    return f"http://127.0.0.1:{port}"


def hide_tunnel_url(text: str, *, replacement: str = "Lokal · :17890") -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if _TUNNEL_HOST_RE.search(raw):
        return replacement
    if "trycloudflare.com" in raw.lower():
        return replacement
    if raw.startswith("http://127.0.0.1") or raw.startswith("http://localhost"):
        return f"Lokal · :{raw.rsplit(':', 1)[-1].rstrip('/')}"
    return raw


def filter_launch_tiles_for_king(tiles: List[Dict[str, Any]], root: Path) -> List[Dict[str, Any]]:
    """Kein Remote+Tunnel doppelt — König sieht nur lokales Cockpit."""
    if not is_king_cockpit_local(root):
        return list(tiles)
    out: List[Dict[str, Any]] = []
    seen_remote = False
    for tile in tiles:
        tid = str(tile.get("id") or "")
        if tid == "tunnel":
            continue
        t = dict(tile)
        if tid == "remote":
            if seen_remote:
                continue
            seen_remote = True
            t["label_de"] = "Worker-Einladung"
            t["value_de"] = "Bereit" if t.get("ok") else "Aus"
            t["detail_de"] = "ULWO unter /download · Mitmachen unter /join"
            out.append(t)
            continue
        if tid == "hub":
            t["detail_de"] = "Lokal · :17890"
        if t.get("detail_de"):
            t["detail_de"] = hide_tunnel_url(str(t["detail_de"]))
        out.append(t)
    return out


def collect_ki_next_steps(root: Path, *, report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """KI-Status + nächste Schritte — immer für Preview nebeneinander."""
    root = Path(root)
    report = dict(report or {})
    system = dict(report.get("system_status") or {})
    chat = dict(report.get("chat_evolution") or {})
    cognitive = dict(system.get("cognitive") or {})

    steps: List[str] = []
    for candidate in (
        str(chat.get("next_step_de") or "").strip(),
        str((system.get("operator") or {}).get("chat_next_de") or "").strip(),
        str((system.get("operator") or {}).get("cockpit_next_step_de") or "").strip(),
    ):
        if candidate and candidate not in steps:
            steps.append(candidate[:220])

    blockers = list(system.get("blockers_de") or report.get("blockers") or [])
    for b in blockers[:2]:
        text = str(b).strip()
        if text and text not in steps:
            steps.append(text[:220])

    if not steps:
        try:
            from analytics.trading_day_cockpit import load_trading_day_cockpit_doc

            td = load_trading_day_cockpit_doc(root) or {}
            nxt = str(td.get("next_step_de") or "").strip()
            if nxt:
                steps.append(nxt[:220])
        except Exception:
            pass

    if not steps:
        steps.append("KI begleitet den Lauf — nächster Schritt nach Preview-Refresh.")

    iface = str(cognitive.get("active_interface") or "—")
    iface_label = {
        "r3_ki": "R3 KI · Cockpit",
        "build_kernel": "Bau-Kernel",
        "build_tool": "Cursor Legacy",
        "cursor_chat": "Cursor Legacy",
        "ollama_local": "Ollama lokal",
        "degraded": "Eingeschränkt",
    }.get(iface, iface)

    return {
        "kernel_active": bool(cognitive.get("successor_active")),
        "kernel_headline_de": str(cognitive.get("headline_de") or system.get("headline_de") or "R3 Kern")[:200],
        "active_interface_de": iface_label,
        "next_step_de": steps[0] if steps else "",
        "next_steps_de": steps[:4],
        "chat_snippet_de": "\n".join(
            ln.strip()
            for ln in str(chat.get("chat_reply_de") or "").splitlines()
            if ln.strip()
        )[:400],
    }
