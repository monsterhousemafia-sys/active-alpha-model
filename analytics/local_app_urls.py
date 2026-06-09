"""Lokale App-URLs — immer 127.0.0.1, keine Tunnel-HTTPS in der UI."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

_HUB_PORT = 17890
_TUNNEL_RE = re.compile(r"https?://[a-z0-9-]+\.trycloudflare\.com", re.I)


def local_hub_url(path: str = "/", *, port: int = _HUB_PORT) -> str:
    p = path if str(path).startswith("/") else f"/{path}"
    return f"http://127.0.0.1:{int(port)}{p}"


def strip_tunnel_urls(text: str, *, replacement: str = "") -> str:
    raw = str(text or "")
    if not raw:
        return ""
    return _TUNNEL_RE.sub(replacement, raw).strip()


def normalize_start_cmd_de(cmd: str, *, port: int = _HUB_PORT) -> str:
    """HTTPS/Tunnel in Startbefehlen durch lokale Hub-URLs ersetzen."""
    raw = str(cmd or "")
    if "trycloudflare.com" in raw.lower() or _TUNNEL_RE.search(raw):
        path = "/join" if "/join" in raw.lower() else "/desktop"
        if "/launch" in raw.lower():
            path = "/launch"
        return local_hub_url(path, port=port)
    raw = strip_tunnel_urls(raw)
    if not raw:
        return ""
    if raw.startswith("http://127.0.0.1") or raw.startswith("http://localhost"):
        return raw
    if raw.startswith("/"):
        return local_hub_url(raw, port=port)
    return raw


def app_start_display_de(root: Path, app: Dict[str, Any], *, port: int = _HUB_PORT) -> str:
    """Anzeige für User — lokale Adresse oder Bash-Befehl, nie Tunnel-HTTPS."""
    root = Path(root)
    aid = str(app.get("id") or "")
    tier = str(app.get("tier") or "")
    hub_path = str(app.get("hub_path") or "").strip()
    start = str(app.get("start_cmd_de") or "").strip()

    if hub_path:
        return local_hub_url(hub_path, port=port)
    if tier == "link":
        return local_hub_url(app.get("hub_path") or "/launch", port=port)
    if aid == "cockpit":
        return local_hub_url("/desktop", port=port)
    if aid == "hub":
        return local_hub_url("/api/health", port=port)
    if aid == "welt":
        return local_hub_url("/launch", port=port)
    if start:
        return normalize_start_cmd_de(start, port=port)
    exec_rel = str(app.get("exec_rel") or "").strip()
    if exec_rel:
        return f"bash {exec_rel}"
    return "—"


def local_join_url(*, port: int = _HUB_PORT) -> str:
    return local_hub_url("/join", port=port)
