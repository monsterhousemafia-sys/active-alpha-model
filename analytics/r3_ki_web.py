"""R3 KI — Internet-Anbindung (sicher, schnell)."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from analytics.r3_ki_storage import load_ki_gui_config

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def _net_cfg(root: Path) -> Dict[str, Any]:
    return (load_ki_gui_config(root).get("internet") or {})


def probe_internet_generic(*, timeout_s: float = 4.0) -> bool:
    try:
        from aa_adaptive_runtime import probe_internet_prices

        if probe_internet_prices(timeout_s=timeout_s):
            return True
    except Exception:
        pass
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.create_connection((host, 53), timeout=timeout_s):
                return True
        except OSError:
            continue
    return False


def _host_blocked(host: str, *, block_private: bool) -> bool:
    if not host:
        return True
    host = host.strip().lower()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if not block_private:
        return False
    try:
        for info in socket.getaddrinfo(host, None):
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
    except (OSError, ValueError):
        return True
    return False


def normalize_fetch_url(url: str) -> Optional[str]:
    raw = str(url or "").strip()
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return raw


def fetch_url_safe(root: Path, url: str) -> Dict[str, Any]:
    root = Path(root)
    cfg = _net_cfg(root)
    if not cfg.get("enabled", True) or not cfg.get("fetch_enabled", True):
        return {"ok": False, "message_de": "Internet-Fetch deaktiviert"}
    norm = normalize_fetch_url(url)
    if not norm:
        return {"ok": False, "message_de": "Ungültige URL"}
    parsed = urlparse(norm)
    if _host_blocked(parsed.hostname or "", block_private=bool(cfg.get("block_private_hosts", True))):
        return {"ok": False, "message_de": "Host nicht erlaubt (lokal/privat blockiert)"}
    max_bytes = int(cfg.get("max_fetch_bytes") or 524_288)
    timeout = float(cfg.get("fetch_timeout_s") or 12.0)
    ua = str(cfg.get("user_agent") or "R3-KI/1.0")
    req = urllib.request.Request(norm, headers={"User-Agent": ua}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = str(resp.headers.get("Content-Type") or "")
            data = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "message_de": f"HTTP {exc.code}", "url": norm}
    except urllib.error.URLError as exc:
        return {"ok": False, "message_de": f"Netzwerk: {exc.reason}", "url": norm}
    except Exception as exc:
        return {"ok": False, "message_de": str(exc)[:200], "url": norm}
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    if "json" in ctype:
        try:
            body = json.dumps(json.loads(data.decode("utf-8", errors="replace")), ensure_ascii=False, indent=0)
        except Exception:
            body = data.decode("utf-8", errors="replace")
    else:
        body = data.decode("utf-8", errors="replace")
    body = re.sub(r"<script[\s\S]*?</script>", "", body, flags=re.IGNORECASE)
    body = re.sub(r"<style[\s\S]*?</style>", "", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    excerpt = body[:4000]
    return {
        "ok": True,
        "url": norm,
        "content_type": ctype,
        "truncated": truncated,
        "excerpt_de": excerpt,
        "headline_de": f"Web: {parsed.netloc} ({len(body)} Zeichen)",
    }


def is_web_command(text: str) -> bool:
    low = str(text or "").strip().lower()
    return low.startswith("/web ") or low.startswith("/fetch ") or low == "/internet"


def is_internet_question(text: str) -> bool:
    """Freitext-Fragen zu Internet/Netz — nicht mit pauschalem Offline-Absage beantworten."""
    raw = str(text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    low = raw.lower()
    keys = (
        "internet",
        "online",
        "webseite",
        "website",
        "netzwerk",
        "anbindung",
        "netz ",
        "http://",
        "https://",
        " url ",
        "fetch",
        "abrufen",
        "herunterladen",
    )
    return any(k in low for k in keys)


def reply_internet_capabilities(root: Path, text: str = "") -> Dict[str, Any]:
    """Ehrliche Internet-Antwort mit Status und Befehlen (Entfaltungsraum)."""
    root = Path(root)
    ok = probe_internet_generic()
    urls = extract_urls(text)
    lines = [
        f"Internet-Status: {'erreichbar ✓' if ok else 'aktuell offline — lokale Tools weiter nutzbar'}",
        "",
        "Im Entfaltungsraum (alpha-model-agent):",
        "  /internet — Verbindung prüfen",
        "  /fetch <url> oder /web <url> — Webseite sicher abrufen",
        "",
        "Ohne Internet: read_file, grep, list_dir, kernel, /bau, ai_kernel-Slash.",
        "Ollama läuft lokal (127.0.0.1) — das ist kein Internet-Blocker.",
    ]
    if urls and ok:
        lines.extend(["", f"Erkannte URL — nutze: /fetch {urls[0]}"])
    elif not ok:
        lines.extend(
            [
                "",
                "Tipp: Netzwerk/WLAN prüfen, dann erneut /internet.",
            ]
        )
    return {
        "ok": True,
        "internet_ok": ok,
        "reply_de": "\n".join(lines),
        "web": True,
    }


def handle_web_command(root: Path, text: str) -> Dict[str, Any]:
    root = Path(root)
    low = str(text or "").strip().lower()
    if low == "/internet":
        ok = probe_internet_generic()
        return {
            "ok": True,
            "internet_ok": ok,
            "reply_de": "Internet: erreichbar" if ok else "Internet: offline — lokale Befehle & Archiv weiter nutzbar",
            "web": True,
        }
    parts = str(text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        return {
            "ok": False,
            "reply_de": "Nutze: /web https://beispiel.de oder /fetch <url>",
            "web": True,
        }
    out = fetch_url_safe(root, parts[1])
    if not out.get("ok"):
        return {**out, "reply_de": out.get("message_de", "Fetch fehlgeschlagen"), "web": True}
    reply = (
        f"{out.get('headline_de')}\nURL: {out.get('url')}\n\n"
        f"{out.get('excerpt_de') or '(leer)'}"
    )
    if out.get("truncated"):
        reply += "\n\n… gekürzt (Max-Größe)"
    return {**out, "reply_de": reply, "web": True}


def extract_urls(text: str) -> list[str]:
    return _URL_RE.findall(str(text or ""))
