"""Preview-Hub Laufzeit — HTTP-Server auf :17890, ohne R3/Qt.

Verantwortung: Daemon, Health, Port. Kein Cockpit-Start, kein Mirror-Cache.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DEFAULT_PORT = 17890
HUB_PRODUCT = "preview-hub"
HUB_SCHEMA_VERSION = 2


def ensure_running(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    restart: bool = False,
) -> int:
    """Hub-Prozess starten oder bestehenden gesunden Listener behalten."""
    from tools.preview_hub import ensure_hub_running

    return int(ensure_hub_running(Path(root), port=int(port), restart=bool(restart)))


def probe_http(
    port: int,
    path: str = "/api/health",
    *,
    host: str = "127.0.0.1",
    timeout: float = 2.0,
) -> bytes:
    try:
        with socket.create_connection((host, int(port)), timeout=float(timeout)) as sock:
            req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            sock.sendall(req)
            chunks: list[bytes] = []
            while True:
                block = sock.recv(65536)
                if not block:
                    break
                chunks.append(block)
        return b"".join(chunks)
    except OSError:
        return b""


def parse_health_body(raw: bytes) -> Dict[str, Any]:
    if not raw or b"\r\n\r\n" not in raw:
        return {}
    _, body = raw.split(b"\r\n\r\n", 1)
    body = body.strip()
    if not body:
        return {}
    try:
        doc = json.loads(body.decode("utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def is_healthy(port: int, *, host: str = "127.0.0.1", timeout: float = 0.8) -> bool:
    """Nur HTTP /api/health — kein R3-Mirror, kein HTML-Render."""
    doc = parse_health_body(probe_http(port, "/api/health", host=host, timeout=timeout))
    if not bool(doc.get("ok")):
        return False
    product = str(doc.get("product") or "")
    if product and product != HUB_PRODUCT:
        return False
    schema = int(doc.get("hub_schema_version") or 0)
    if schema and schema < HUB_SCHEMA_VERSION:
        return False
    return True


def probe_route(
    port: int,
    path: str,
    *,
    host: str = "127.0.0.1",
    timeout: float = 2.0,
) -> Tuple[bool, str]:
    raw = probe_http(port, path, host=host, timeout=timeout)
    if not raw:
        return False, "timeout"
    head = raw.split(b"\r\n", 1)[0].decode("ascii", errors="ignore")
    if " 200 " in head or " 302 " in head:
        return True, head.split(" ", 2)[1] if " " in head else "200"
    if " 404 " in head:
        return False, "404"
    return False, head[:80] or "empty"


def build_health_report(root: Path, *, port: int = DEFAULT_PORT) -> Dict[str, Any]:
    root = Path(root)
    online = is_healthy(port)
    route_login, login_detail = probe_route(port, "/login") if online else (False, "offline")
    return {
        "ok": online,
        "layer": "hub",
        "port": int(port),
        "product": HUB_PRODUCT,
        "hub_schema_version": HUB_SCHEMA_VERSION,
        "online": online,
        "route_login_ok": route_login,
        "route_login_detail": login_detail,
        "ensure_cmd_de": "python3 tools/preview_hub.py --ensure",
    }
