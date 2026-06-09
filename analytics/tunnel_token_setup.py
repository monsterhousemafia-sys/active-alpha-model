"""Cloudflare-Tunnel-Token — server.env anwenden, Wizard-Status."""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_SERVER_ENV = Path("control/server.env")
_TOKEN_REL = Path("control/cloudflare_tunnel.token")
_TUNNEL_CFG_REL = Path("control/cloudflare_tunnel.json")
_CERT_CANDIDATES = (
    Path.home() / ".cloudflared/cert.pem",
    Path.home() / ".cloudflared/cert.json",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_server_env(root: Path) -> Dict[str, str]:
    root = Path(root)
    out: Dict[str, str] = {}
    path = root / _SERVER_ENV
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def has_cloudflared_cert() -> bool:
    return any(p.is_file() for p in _CERT_CANDIDATES)


def cloudflared_login_url(root: Path) -> str:
    from analytics.remote_hub_access import cloudflared_path

    cf = cloudflared_path(root)
    if cf:
        try:
            proc = subprocess.run(
                [str(cf), "tunnel", "login"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for line in (proc.stdout or "").splitlines() + (proc.stderr or "").splitlines():
                if "https://" in line:
                    for part in line.split():
                        if part.startswith("https://"):
                            return part.rstrip(".")
        except (OSError, subprocess.TimeoutExpired):
            pass
    return "https://dash.cloudflare.com/login"


def wizard_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    env = load_server_env(root)
    token_in_env = bool(str(env.get("AA_CLOUDFLARE_TUNNEL_TOKEN") or "").strip())
    url_in_env = bool(str(env.get("AA_CLOUDFLARE_TUNNEL_URL") or "").strip())
    token_file = (root / _TOKEN_REL).is_file()
    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "server_env_exists": (root / _SERVER_ENV).is_file(),
        "token_in_server_env": token_in_env,
        "url_in_server_env": url_in_env,
        "token_file": token_file,
        "cloudflared_cert": has_cloudflared_cert(),
        "steps_de": [
            "1. cp control/server.env.example control/server.env",
            "2. Cloudflare Zero Trust: Tunnel → Public Hostname http://127.0.0.1:17890",
            "3. AA_CLOUDFLARE_TUNNEL_TOKEN + AA_CLOUDFLARE_TUNNEL_URL eintragen",
            "4. bash tools/setup_cloudflare_tunnel_token.sh",
            "5. bash tools/king_ops.sh spread voll && bash tools/king_ops.sh whatsapp durch",
        ],
        "headline_de": (
            "Token in server.env — setup_cloudflare_tunnel_token.sh ausführen"
            if token_in_env and url_in_env
            else "server.env anlegen — Token + stabile HTTPS-URL eintragen"
        ),
    }


def apply_tunnel_token(
    root: Path,
    *,
    token: str,
    url: str,
    passphrase: str = "",
) -> Dict[str, Any]:
    root = Path(root)
    token = str(token or "").strip()
    url = str(url or "").strip().rstrip("/")
    if len(token) < 20:
        return {"ok": False, "message_de": "Token zu kurz"}
    if not url.startswith("https://"):
        return {"ok": False, "message_de": "HTTPS-URL Pflicht"}

    token_path = root / _TOKEN_REL
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token + "\n", encoding="utf-8")
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass

    cfg_path = root / _TUNNEL_CFG_REL
    atomic_write_json(
        cfg_path,
        {
            "schema_version": 1,
            "public_hostname": url,
            "public_url": url,
            "stable": True,
            "updated_at_utc": _utc_now(),
        },
    )

    env_path = root / _SERVER_ENV
    lines = []
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(("AA_CLOUDFLARE_TUNNEL_TOKEN=", "AA_CLOUDFLARE_TUNNEL_URL=")):
                continue
            lines.append(line)
    lines.extend(
        [
            f"AA_CLOUDFLARE_TUNNEL_TOKEN={token}",
            f"AA_CLOUDFLARE_TUNNEL_URL={url}",
        ]
    )
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass

    return {"ok": True, "encrypted": False, "public_url": url, "message_de": "Token gespeichert"}


def apply_from_server_env(root: Path) -> Dict[str, Any]:
    root = Path(root)
    env = load_server_env(root)
    token = str(env.get("AA_CLOUDFLARE_TUNNEL_TOKEN") or os.environ.get("AA_CLOUDFLARE_TUNNEL_TOKEN") or "").strip()
    url = str(env.get("AA_CLOUDFLARE_TUNNEL_URL") or os.environ.get("AA_CLOUDFLARE_TUNNEL_URL") or "").strip().rstrip("/")
    if not token or not url:
        return {
            "ok": False,
            "message_de": "control/server.env fehlt oder Token/URL leer — wizard_status prüfen",
            "wizard": wizard_status(root),
        }
    applied = apply_tunnel_token(root, token=token, url=url)
    if not applied.get("ok"):
        return applied
    from analytics.remote_hub_access import ensure_remote_hub_url

    remote = ensure_remote_hub_url(root, mode="cloudflared-token")
    return {
        "ok": bool(remote.get("ok")),
        "tunnel_stable": True,
        "public_base_url": remote.get("public_base_url") or url,
        "remote": remote,
        "message_de": (
            f"Stabiler Tunnel aktiv — {remote.get('public_base_url') or url}"
            if remote.get("ok")
            else str(remote.get("message_de") or "Tunnel-Start fehlgeschlagen")
        ),
    }
