"""Separater lokaler Zugang für Schlüssel — nur 127.0.0.1, nie Chat/Remote."""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

from aa_safe_io import atomic_write_json

_KEYRING_SERVICE = "active-alpha-credential-vault"


def _keyring_account(root: Path, name: str) -> str:
    import hashlib

    digest = hashlib.sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:16]
    return f"{digest}:{name}"
_DEFAULT_PORT = 17891
_SESSION_TTL_S = 900
_EVIDENCE_REL = Path("evidence/secure_vault_portal.json")
_SESSIONS_REL = Path("evidence/vault_sessions.json")

_rate_limit: Dict[str, Dict[str, Any]] = {}
_MAX_FAILS = 5
_LOCKOUT_S = 300


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    """Nur echte Socket-Adresse — Proxies/Forwarded-Header werden ignoriert."""
    return str(handler.client_address[0] or "")


def is_localhost_client(handler: BaseHTTPRequestHandler) -> bool:
    ip = _client_ip(handler)
    if ip in ("127.0.0.1", "::1", "localhost"):
        return True
    if ip.startswith("::ffff:127."):
        return True
    return False


def _deny_remote(handler: BaseHTTPRequestHandler) -> bool:
    if is_localhost_client(handler):
        return False
    body = json.dumps(
        {"ok": False, "message_de": "Vault nur lokal — kein Remote-Zugriff"},
        ensure_ascii=False,
    ).encode("utf-8")
    handler.send_response(403)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _sessions_path(root: Path) -> Path:
    return Path(root) / _SESSIONS_REL


@contextmanager
def _session_store(root: Path):
    root = Path(root)
    path = _sessions_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read()
        try:
            doc = json.loads(raw or "{}")
            sessions = dict(doc.get("sessions") or {}) if isinstance(doc, dict) else {}
        except json.JSONDecodeError:
            sessions = {}
        now = time.time()
        dead = [k for k, meta in sessions.items() if float(meta.get("exp") or 0) <= now]
        for k in dead:
            sessions.pop(k, None)
        yield sessions
        fh.seek(0)
        fh.truncate()
        fh.write(
            json.dumps(
                {"schema_version": 1, "updated_at_utc": _utc_now(), "sessions": sessions},
                ensure_ascii=False,
            )
        )
        fh.flush()
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _issue_session(
    root: Path,
    *,
    mode: str = "setup",
    reason_de: str = "",
    client_ip: str = "127.0.0.1",
) -> str:
    root = Path(root)
    sid = secrets.token_urlsafe(32)
    with _session_store(root) as sessions:
        sessions[sid] = {
            "exp": time.time() + _SESSION_TTL_S,
            "mode": str(mode or "setup"),
            "reason_de": str(reason_de or ""),
            "client_ip": str(client_ip or "127.0.0.1"),
        }
    return sid


def _session_valid(root: Path, sid: str, *, client_ip: str = "") -> bool:
    with _session_store(root) as sessions:
        meta = sessions.get(str(sid or "").strip()) or {}
        if float(meta.get("exp") or 0) <= time.time():
            return False
        bound = str(meta.get("client_ip") or "")
        if bound and client_ip and bound != client_ip:
            return False
        return True


def _touch_session(root: Path, sid: str, **fields: Any) -> None:
    with _session_store(root) as sessions:
        meta = sessions.get(str(sid or "").strip())
        if not meta:
            return
        meta.update(fields)
        sessions[sid] = meta


def _rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    bucket = _rate_limit.get(client_ip) or {"fails": 0, "until": 0.0}
    if float(bucket.get("until") or 0) > now:
        return True
    _rate_limit[client_ip] = bucket
    return False


def _record_fail(client_ip: str) -> None:
    bucket = _rate_limit.get(client_ip) or {"fails": 0, "until": 0.0}
    bucket["fails"] = int(bucket.get("fails") or 0) + 1
    if bucket["fails"] >= _MAX_FAILS:
        bucket["until"] = time.monotonic() + _LOCKOUT_S
        bucket["fails"] = 0
    _rate_limit[client_ip] = bucket


def _security_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
    handler.send_header("Referrer-Policy", "no-referrer")


def _session_meta(root: Path, sid: str) -> Dict[str, Any]:
    with _session_store(root) as sessions:
        return dict(sessions.get(str(sid or "").strip()) or {})


def keyring_set(root: Path, name: str, value: str) -> bool:
    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, _keyring_account(root, name), str(value or ""))
        return True
    except Exception:
        return False


def keyring_get(root: Path, name: str) -> str:
    try:
        import keyring

        return str(keyring.get_password(_KEYRING_SERVICE, _keyring_account(root, name)) or "").strip()
    except Exception:
        return ""


def keyring_delete(root: Path, name: str) -> bool:
    try:
        import keyring

        keyring.delete_password(_KEYRING_SERVICE, _keyring_account(root, name))
        return True
    except Exception:
        return False


def store_tunnel_credentials(
    root: Path,
    *,
    token: str,
    url: str,
    manage: bool = False,
    passphrase: str = "",
    auto_provision: bool = False,
) -> Dict[str, Any]:
    """Token verschlüsselt speichern — danach vollständiger Login-Abschluss."""
    from analytics.cloudflare_login_flow import (
        complete_login_pipeline,
        fetch_token_from_cloudflare_cli,
        resolve_public_url,
    )
    from analytics.tunnel_secret_vault import harden_secret_paths, purge_plaintext_secrets
    from analytics.tunnel_token_setup import apply_tunnel_token
    from analytics.vault_passphrase import validate_passphrase

    root = Path(root)
    token = str(token or "").strip()
    url = resolve_public_url(root, str(url or "").strip().rstrip("/"))
    pw_err = validate_passphrase(passphrase)
    if pw_err:
        return {"ok": False, "message_de": pw_err}
    if manage and not token:
        token = load_tunnel_token_from_portal(root)
    if (not token or len(token) < 20) and auto_provision:
        fetched = fetch_token_from_cloudflare_cli(root)
        if not fetched.get("ok"):
            return fetched
        token = str(fetched.get("token") or "")
    if not url:
        url = keyring_get(root, "cloudflare_tunnel_url")
    if len(token) < 20 or not url.startswith("https://"):
        return {
            "ok": False,
            "message_de": "Token fehlt — „Automatisch laden“ aktivieren oder Token einfügen; HTTPS-URL Pflicht",
        }

    keyring_delete(root, "cloudflare_tunnel_token")
    kr_url = keyring_set(root, "cloudflare_tunnel_url", url)
    applied = apply_tunnel_token(root, token=token, url=url, passphrase=passphrase)
    if not applied.get("ok"):
        return applied
    purge_plaintext_secrets(root)
    harden_secret_paths(root)

    completion = complete_login_pipeline(root)
    pipeline_ok = bool(completion.get("ok"))
    return {
        "ok": True,
        "pipeline_ok": pipeline_ok,
        "plaintext_keyring_token": False,
        "keyring_url": kr_url,
        "encrypted_vault": applied.get("encrypted"),
        "public_url": url,
        "remote_ok": pipeline_ok,
        "login_complete": completion,
        "message_de": (
            str(completion.get("headline_de") or "Gesichert — Tunnel wird aktiviert")
            if pipeline_ok
            else "Gespeichert — ai_kernel cloudflare-login-complete für Remote-Check"
        ),
    }


def load_tunnel_token_from_portal(root: Path) -> str:
    root = Path(root)
    keyring_delete(root, "cloudflare_tunnel_token")
    try:
        from analytics.tunnel_secret_vault import load_token_decrypted

        return load_token_decrypted(root)
    except Exception:
        return ""


def keyring_available() -> bool:
    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, "__probe__", "1")
        keyring.delete_password(_KEYRING_SERVICE, "__probe__")
        return True
    except Exception:
        return False


def credential_action_needed(root: Path, *, force_manage: bool = False) -> Dict[str, Any]:
    """Prüft, ob Schlüssel-Tresor geöffnet werden muss."""
    root = Path(root)
    if force_manage:
        return {
            "needed": True,
            "mode": "manage",
            "reason_de": "Schlüssel verwalten oder ändern",
        }
    st = portal_status(root)
    if not st.get("tunnel_configured"):
        try:
            from analytics.tunnel_token_setup import has_cloudflared_cert

            cert = has_cloudflared_cert()
        except Exception:
            cert = False
        if not cert:
            return {
                "needed": True,
                "mode": "setup",
                "reason_de": "Cloudflare-Anmeldung und Tunnel-Token einrichten",
                "cloudflare_login": True,
            }
        return {
            "needed": True,
            "mode": "setup",
            "reason_de": "Tunnel-Token und öffentliche URL eintragen",
        }
    try:
        from analytics.tunnel_secret_vault import vault_status

        vs = vault_status(root)
        if vs.get("legacy_plaintext_token") or vs.get("server_env_has_plaintext_token"):
            return {
                "needed": True,
                "mode": "migrate",
                "reason_de": "Klartext-Schlüssel in verschlüsselten Vault überführen",
            }
    except Exception:
        pass
    return {"needed": False, "mode": "ok", "reason_de": ""}


def ensure_vault_server_running(root: Path, *, port: int = _DEFAULT_PORT) -> bool:
    root = Path(root)
    if port_listening(port):
        return True
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)
    script = root / "tools/secure_vault_server.py"
    if not script.is_file():
        return False
    subprocess.Popen(
        [str(py), str(script), "--daemon", "--port", str(port)],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.45)
    return port_listening(port)


def launch_vault_in_browser(url: str) -> bool:
    url = str(url or "").strip()
    if not url.startswith("http://127.0.0.1:"):
        return False
    for cmd in (["xdg-open", url], ["gio", "open", url], ["sensible-browser", url]):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    return False


def portal_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    token = load_tunnel_token_from_portal(root)
    url = keyring_get(root, "cloudflare_tunnel_url")
    if not url:
        try:
            from analytics.tunnel_token_setup import load_server_env

            url = str(load_server_env(root).get("AA_CLOUDFLARE_TUNNEL_URL") or "").strip()
        except Exception:
            url = ""
    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "portal_port": _DEFAULT_PORT,
        "localhost_only": True,
        "keyring_available": keyring_available(),
        "tunnel_configured": bool(token and url),
        "public_url": url or None,
        "message_de": (
            "Schlüssel sind gesichert — nur auf diesem Gerät."
            if token
            else "Schlüssel-Tresor öffnet sich bei Bedarf automatisch."
        ),
    }


def _render_vault_page(
    *,
    session: str,
    ok: Optional[bool] = None,
    msg: str = "",
    mode: str = "setup",
    reason_de: str = "",
    cloudflare_login_url: str = "",
    existing_url: str = "",
    active_step: int = 1,
    form_action: str = "/local/vault/store",
) -> bytes:
    from analytics.vault_portal_ui import render_vault_page

    return render_vault_page(
        session=session,
        ok=ok,
        msg=msg,
        mode=mode,
        reason_de=reason_de,
        cloudflare_login_url=cloudflare_login_url,
        existing_url=existing_url,
        active_step=active_step,
        form_action=form_action,
    )


def _parse_form(body: bytes) -> Dict[str, str]:
    from urllib.parse import unquote_plus

    out: Dict[str, str] = {}
    text = body.decode("utf-8", errors="replace")
    for part in text.split("&"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[unquote_plus(k)] = unquote_plus(v)
    return out


def make_vault_handler(root: Path):
    root = Path(root)

    class VaultHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_GET(self) -> None:
            if _deny_remote(self):
                return
            path = urlparse(self.path).path
            ip = _client_ip(self)
            if path == "/api/vault/status":
                body = json.dumps(portal_status(root), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                _security_headers(self)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path in ("/", "/vault"):
                qs = parse_qs(urlparse(self.path).query)
                sid = (qs.get("session") or [""])[0]
                _touch_session(root, sid, client_ip=ip)
                if not _session_valid(root, sid, client_ip=ip):
                    body = _render_vault_page(
                        session="",
                        ok=False,
                        msg="Sitzung abgelaufen — Tresor öffnet sich erneut.",
                    )
                    self.send_response(403)
                else:
                    meta = _session_meta(root, sid)
                    mode = str(meta.get("mode") or "setup")
                    reason = str(meta.get("reason_de") or "")
                    cf_url = ""
                    if meta.get("cloudflare_login"):
                        try:
                            from analytics.tunnel_token_setup import cloudflared_login_url

                            cf_url = cloudflared_login_url(root)
                        except Exception:
                            cf_url = "https://dash.cloudflare.com/login"
                    existing = keyring_get(root, "cloudflare_tunnel_url")
                    active = 1 if meta.get("cloudflare_login") else 2
                    body = _render_vault_page(
                        session=sid,
                        mode=mode,
                        reason_de=reason,
                        cloudflare_login_url=cf_url,
                        existing_url=existing,
                        active_step=active,
                        form_action="/api/vault/store",
                    )
                    self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                _security_headers(self)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if _deny_remote(self):
                return
            ip = _client_ip(self)
            if _rate_limited(ip):
                body = _render_vault_page(session="", ok=False, msg="Zu viele Versuche — 5 Minuten warten.")
                self.send_response(429)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                _security_headers(self)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            path = urlparse(self.path).path
            if path != "/api/vault/store":
                self.send_error(404)
                return
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            if str(self.headers.get("Content-Type") or "").startswith("application/json"):
                try:
                    data = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    data = {}
            else:
                data = _parse_form(raw)
            sid = str(data.get("session") or self.headers.get("X-Vault-Session") or "")
            if not _session_valid(root, sid, client_ip=ip):
                _record_fail(ip)
                body = _render_vault_page(session="", ok=False, msg="Sitzung abgelaufen — Tresor öffnet sich erneut.")
                self.send_response(403)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                _security_headers(self)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
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
                _record_fail(ip)
            body = _render_vault_page(
                session=sid,
                ok=bool(out.get("pipeline_ok") or out.get("ok")),
                msg=str(out.get("message_de") or ""),
                active_step=3 if out.get("ok") else 2,
                form_action="/api/vault/store",
            )
            code = 200 if out.get("ok") else 400
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            _security_headers(self)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return VaultHandler


def run_vault_server(root: Path, *, port: int = _DEFAULT_PORT, bind: str = "127.0.0.1") -> ThreadingHTTPServer:
    handler = make_vault_handler(root)
    server = ThreadingHTTPServer((bind, port), handler)
    return server


def _hub_vault_url(root: Path, session_id: str) -> Tuple[str, int]:
    """Hub-URL für Tresor — sichtbar im Cursor-Browser."""
    try:
        from tools.preview_hub import ensure_hub_running

        hub_port = int(ensure_hub_running(root, restart=False))
    except Exception:
        try:
            from analytics.preview_federation import federation_config

            hub_port = int(federation_config(root).get("hub_port") or 17890)
        except Exception:
            hub_port = 17890
    return f"http://127.0.0.1:{hub_port}/local/vault?session={session_id}", hub_port


def open_portal(
    root: Path,
    *,
    port: int = _DEFAULT_PORT,
    mode: str = "setup",
    reason_de: str = "",
    cloudflare_login: bool = False,
) -> Dict[str, Any]:
    """Session erzeugen und lokalen Vault-URL zurückgeben."""
    root = Path(root)
    sid = _issue_session(root, mode=mode, reason_de=reason_de)
    if cloudflare_login:
        _touch_session(root, sid, cloudflare_login=True)
    hub_url, hub_port = _hub_vault_url(root, sid)
    direct_url = f"http://127.0.0.1:{port}/vault?session={sid}"
    doc = {
        "ok": True,
        "portal_url": hub_url,
        "vault_direct_url": direct_url,
        "hub_port": hub_port,
        "mode": mode,
        "reason_de": reason_de or None,
        "localhost_only": True,
        "session_ttl_s": _SESSION_TTL_S,
        "message_de": "Schlüssel-Tresor bereit — nur auf diesem Gerät.",
        "security_de": "Privatsphäre zuerst. Nicht im Chat.",
    }
    atomic_write_json(root / _EVIDENCE_REL, {**doc, "updated_at_utc": _utc_now(), "session_active": True})
    return doc


def reveal_vault_portal(
    root: Path,
    *,
    reason_de: str = "",
    mode: str = "setup",
    cloudflare_login: bool = False,
    auto_open_browser: bool = True,
    port: int = _DEFAULT_PORT,
) -> Dict[str, Any]:
    """Tresor-Server starten, Session erzeugen, Browser automatisch öffnen."""
    root = Path(root)
    ensure_vault_server_running(root, port=port)
    doc = open_portal(
        root,
        port=port,
        mode=mode,
        reason_de=reason_de,
        cloudflare_login=cloudflare_login,
    )
    opened = False
    if auto_open_browser and not os.environ.get("AA_VAULT_NO_AUTO_OPEN"):
        opened = launch_vault_in_browser(str(doc.get("portal_url") or ""))
    doc["portal_opened"] = opened
    doc["message_de"] = (
        "Schlüssel-Tresor geöffnet — nur auf diesem Gerät."
        if opened
        else "Schlüssel-Tresor bereit — portal_url lokal öffnen."
    )
    atomic_write_json(root / _EVIDENCE_REL, {**doc, "updated_at_utc": _utc_now()})
    return doc


def auto_open_if_needed(
    root: Path,
    *,
    context: str = "",
    force_manage: bool = False,
) -> Optional[Dict[str, Any]]:
    """Öffnet Tresor automatisch, wenn Eingabe/Verwaltung nötig ist."""
    root = Path(root)
    need = credential_action_needed(root, force_manage=force_manage)
    if not need.get("needed"):
        return None
    doc = reveal_vault_portal(
        root,
        reason_de=str(need.get("reason_de") or context or "Schlüssel erforderlich"),
        mode=str(need.get("mode") or "setup"),
        cloudflare_login=bool(need.get("cloudflare_login")),
    )
    doc["auto_open_context"] = context or None
    return doc


def port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False
