"""Vault über Hub-Port — nur localhost, sichtbar im Cursor-Browser."""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs, urlparse


def is_localhost_ip(ip: str) -> bool:
    ip = str(ip or "")
    return ip in ("127.0.0.1", "::1", "localhost") or ip.startswith("::ffff:127.")


def handle_vault_request(
    root,
    *,
    method: str,
    path: str,
    query: str,
    client_ip: str,
    content_type: str = "",
    body: bytes = b"",
) -> Tuple[int, str, bytes]:
    """Gibt (status, content_type, body) zurück — nur für 127.0.0.1."""
    from analytics.secure_credential_portal import (
        _parse_form,
        _rate_limited,
        _record_fail,
        _render_vault_page,
        _session_meta,
        _session_valid,
        _touch_session,
        keyring_get,
        portal_status,
        store_tunnel_credentials,
    )

    if not is_localhost_ip(client_ip):
        payload = json.dumps({"ok": False, "message_de": "Nur localhost"}, ensure_ascii=False).encode("utf-8")
        return 403, "application/json; charset=utf-8", payload

    path = str(path or "")
    qs = parse_qs(str(query or ""))

    if method == "GET" and path == "/local/vault/status":
        raw = json.dumps(portal_status(root), ensure_ascii=False).encode("utf-8")
        return 200, "application/json; charset=utf-8", raw

    if method == "GET" and path == "/local/vault":
        sid = (qs.get("session") or [""])[0]
        _touch_session(root, sid, client_ip=client_ip)
        if not _session_valid(root, sid, client_ip=client_ip):
            body_html = _render_vault_page(
                session="",
                ok=False,
                msg="Sitzung abgelaufen — ai_kernel cloudflare-login-plan erneut",
                active_step=1,
            )
            return 403, "text/html; charset=utf-8", body_html
        meta = _session_meta(root, sid)
        mode = str(meta.get("mode") or "setup")
        cf_url = ""
        if meta.get("cloudflare_login"):
            try:
                from analytics.tunnel_token_setup import cloudflared_login_url

                cf_url = cloudflared_login_url(root)
            except Exception:
                cf_url = "https://dash.cloudflare.com/login"
        existing = keyring_get(root, "cloudflare_tunnel_url")
        active = 1 if meta.get("cloudflare_login") else 2
        body_html = _render_vault_page(
            session=sid,
            mode=mode,
            reason_de=str(meta.get("reason_de") or ""),
            cloudflare_login_url=cf_url,
            existing_url=existing,
            active_step=active,
        )
        return 200, "text/html; charset=utf-8", body_html

    if method == "POST" and path == "/local/vault/store":
        if _rate_limited(client_ip):
            body_html = _render_vault_page(session="", ok=False, msg="Zu viele Versuche — 5 Min. warten.")
            return 429, "text/html; charset=utf-8", body_html
        if str(content_type).startswith("application/json"):
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                data = {}
        else:
            data = _parse_form(body)
        sid = str(data.get("session") or "")
        if not _session_valid(root, sid, client_ip=client_ip):
            _record_fail(client_ip)
            body_html = _render_vault_page(session="", ok=False, msg="Sitzung abgelaufen")
            return 403, "text/html; charset=utf-8", body_html
        meta = _session_meta(root, sid)
        mode = str(meta.get("mode") or "setup")
        auto = str(data.get("auto_provision") or "").lower() in ("1", "true", "on", "yes")
        out = store_tunnel_credentials(
            root,
            token=str(data.get("tunnel_token") or ""),
            url=str(data.get("tunnel_url") or ""),
            manage=mode == "manage",
            passphrase=str(data.get("vault_passphrase") or ""),
            auto_provision=auto,
        )
        if not out.get("ok"):
            _record_fail(client_ip)
        body_html = _render_vault_page(
            session=sid,
            ok=bool(out.get("pipeline_ok") or out.get("ok")),
            msg=str(out.get("message_de") or ""),
            active_step=3 if out.get("ok") else 2,
            form_action="/local/vault/store",
        )
        return (200 if out.get("ok") else 400), "text/html; charset=utf-8", body_html

    return 404, "text/plain; charset=utf-8", b"not found"
