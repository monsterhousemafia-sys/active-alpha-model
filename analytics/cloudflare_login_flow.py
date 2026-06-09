"""Vollständiger Cloudflare-Login — Plan, OAuth, Vault, Tunnel, Verifikation."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_TUNNEL_NAME = "active-alpha-hub"
_EVIDENCE_PLAN = Path("evidence/cloudflare_login_plan.json")
_EVIDENCE_COMPLETE = Path("evidence/cloudflare_login_complete.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _http_ok(url: str, *, timeout: float = 8.0) -> Dict[str, Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "active-alpha-login-check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(512).decode("utf-8", errors="replace")
            return {"ok": resp.status == 200, "status": resp.status, "body": body[:200]}
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {"ok": False, "error": str(exc)[:200]}


def plan_login_flow(root: Path) -> Dict[str, Any]:
    """Aktueller Stand + Schritte für reibungslosen Login."""
    from analytics.secure_credential_portal import portal_status
    from analytics.tunnel_autologin_setup import cert_path, login_url
    from analytics.tunnel_secret_vault import load_token_decrypted, vault_status

    root = Path(root)
    cert = cert_path().is_file()
    vs = vault_status(root)
    token = bool(load_token_decrypted(root))
    st = portal_status(root)
    url = str(st.get("public_url") or "").strip()

    steps: List[Dict[str, Any]] = [
        {
            "id": "oauth",
            "label_de": "Cloudflare anmelden (Browser)",
            "done": cert,
            "action_de": "Im Tresor: „Cloudflare öffnen“ — Passwort nur dort",
        },
        {
            "id": "vault",
            "label_de": "Token, URL + Tresor-Passphrase im Schlüssel-Tresor",
            "done": token and bool(url),
            "action_de": "Tresor öffnet sich automatisch — ai_kernel vault-open",
        },
        {
            "id": "tunnel",
            "label_de": "Tunnel starten + Remote prüfen",
            "done": False,
            "action_de": "Läuft automatisch nach „Sichern“ im Tresor",
        },
    ]

    phase = "oauth"
    if cert and not (token and url):
        phase = "vault"
    elif token and url:
        phase = "tunnel"

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "phase": phase,
        "cloudflare_cert": cert,
        "vault_configured": token and bool(url),
        "public_url": url or None,
        "login_url": login_url(root),
        "steps": steps,
        "headline_de": (
            "Bereit — Daten im Tresor speichern, Rest läuft automatisch"
            if phase == "vault" and cert
            else (
                "Zuerst bei Cloudflare anmelden"
                if not cert
                else "Tunnel wird nach Tresor-Speichern aktiviert"
            )
        ),
    }
    atomic_write_json(root / _EVIDENCE_PLAN, doc)
    return doc


def fetch_token_from_cloudflare_cli(root: Path) -> Dict[str, Any]:
    """Nach OAuth: Tunnel per cloudflared CLI anlegen und Token holen."""
    from analytics.remote_hub_access import cloudflared_path
    from analytics.tunnel_autologin_setup import cert_path

    root = Path(root)
    if not cert_path().is_file():
        return {
            "ok": False,
            "message_de": "Cloudflare-Login fehlt — zuerst im Browser anmelden",
        }
    cf = cloudflared_path(root)
    if not cf:
        return {"ok": False, "message_de": "cloudflared nicht installiert"}

    try:
        listed = subprocess.run(
            [str(cf), "tunnel", "list", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        exists = False
        if listed.returncode == 0 and listed.stdout.strip():
            try:
                for row in json.loads(listed.stdout):
                    if str(row.get("name") or "") == _TUNNEL_NAME:
                        exists = True
                        break
            except json.JSONDecodeError:
                exists = _TUNNEL_NAME in (listed.stdout or "")
        if not exists:
            created = subprocess.run(
                [str(cf), "tunnel", "create", _TUNNEL_NAME],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if created.returncode != 0:
                return {
                    "ok": False,
                    "message_de": "Tunnel-Erstellung fehlgeschlagen — Cloudflare-Konto prüfen",
                }
        tok_proc = subprocess.run(
            [str(cf), "tunnel", "token", _TUNNEL_NAME],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        token = (tok_proc.stdout or "").strip()
        if tok_proc.returncode != 0 or len(token) < 20:
            return {"ok": False, "message_de": "Token-Abruf fehlgeschlagen — erneut anmelden"}
        return {"ok": True, "token": token, "tunnel_name": _TUNNEL_NAME}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message_de": "Cloudflare-CLI Timeout"}


def resolve_public_url(root: Path, user_url: str) -> str:
    user_url = str(user_url or "").strip().rstrip("/")
    if user_url.startswith("https://"):
        return user_url
    try:
        from analytics.preview_federation import federation_config

        cfg = federation_config(root)
        locked = str(cfg.get("public_base_url") or "").strip().rstrip("/")
        if cfg.get("public_base_url_locked") and locked.startswith("https://"):
            return locked
    except Exception:
        pass
    try:
        from analytics.remote_hub_access import load_stable_tunnel_url

        stable = load_stable_tunnel_url(root)
        if stable.startswith("https://"):
            return stable
    except Exception:
        pass
    return user_url


def complete_login_pipeline(root: Path) -> Dict[str, Any]:
    """Nach Tresor-Eingabe: Hub, Tunnel, Remote — vollständig verifizieren."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    try:
        from tools.preview_hub import ensure_hub_running

        port = ensure_hub_running(root, restart=False)
        steps.append({"step": "hub", "ok": True, "port": port})
    except Exception as exc:
        steps.append({"step": "hub", "ok": False, "error": str(exc)[:120]})
        port = 17890

    try:
        subprocess.run(
            ["bash", str(root / "tools/install_cloudflared.sh")],
            cwd=str(root),
            capture_output=True,
            timeout=120,
            check=False,
        )
        steps.append({"step": "cloudflared", "ok": True})
    except Exception as exc:
        steps.append({"step": "cloudflared", "ok": False, "error": str(exc)[:120]})

    remote: Dict[str, Any] = {"ok": False}
    status: Dict[str, Any] = {}
    try:
        from analytics.remote_hub_access import ensure_remote_hub_url, remote_access_status

        remote = ensure_remote_hub_url(root, mode="cloudflared-token")
        status = remote_access_status(root)
        steps.append({"step": "remote_tunnel", "ok": bool(remote.get("ok")), "detail": remote})
    except Exception as exc:
        steps.append({"step": "remote_tunnel", "ok": False, "error": str(exc)[:120]})

    local_health = _http_ok(f"http://127.0.0.1:{port}/api/health")
    steps.append({"step": "local_health", "ok": bool(local_health.get("ok"))})

    public_url = str(remote.get("public_base_url") or resolve_public_url(root, "") or "").rstrip("/")
    remote_health: Dict[str, Any] = {"ok": False}
    if public_url.startswith("https://"):
        time.sleep(2.0)
        remote_health = _http_ok(f"{public_url}/api/health")
    steps.append({"step": "remote_health", "ok": bool(remote_health.get("ok")), "url": public_url})

    try:
        from analytics.vault_airgap import verify_airgap

        airgap = verify_airgap(root)
        steps.append({"step": "airgap", "ok": bool(airgap.get("ok"))})
    except Exception as exc:
        airgap = {"ok": False}
        steps.append({"step": "airgap", "ok": False, "error": str(exc)[:80]})

    ok = bool(
        local_health.get("ok")
        and remote.get("ok")
        and remote_health.get("ok")
    )
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok,
        "public_url": public_url or None,
        "local_health": local_health,
        "remote_health": remote_health,
        "remote": remote,
        "status": status,
        "steps": steps,
        "headline_de": (
            f"Login abgeschlossen — {public_url} erreichbar"
            if ok
            else "Daten gespeichert — Tunnel/Remote noch prüfen (ai_kernel cloudflare-login-complete)"
        ),
    }
    atomic_write_json(root / _EVIDENCE_COMPLETE, doc)
    plan_login_flow(root)
    return doc


def run_after_vault_save(root: Path) -> Dict[str, Any]:
    """Direkt nach erfolgreichem Tresor-Speichern aufrufen."""
    return complete_login_pipeline(root)
