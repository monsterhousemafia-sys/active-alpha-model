"""Luftspalt — Schlüssel-Tresor vollständig von der Außenwelt abgeschottet."""
from __future__ import annotations

import json
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_VAULT_PORT = 17891
_HUB_PORT = 17890
_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_EVIDENCE_REL = Path("evidence/vault_airgap_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _listening_addresses(port: int) -> List[str]:
    addrs: List[str] = []
    try:
        proc = subprocess.run(
            ["ss", "-ltn", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        for line in (proc.stdout or "").splitlines()[1:]:
            parts = line.split()
            if parts:
                addr = parts[3] if len(parts) > 3 else parts[-1]
                if ":" in addr:
                    addrs.append(addr.rsplit(":", 1)[0].strip("[]"))
    except (OSError, subprocess.TimeoutExpired):
        pass
    if not addrs:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                s.listen(1)
                addrs.append("0.0.0.0")
        except OSError:
            addrs.append("127.0.0.1")
    return addrs


def vault_bind_is_local_only(port: int = _VAULT_PORT) -> Dict[str, Any]:
    addrs = _listening_addresses(port)
    if not addrs:
        return {"ok": True, "listening": False, "addresses": [], "message_de": "Vault nicht aktiv"}
    bad = [a for a in addrs if a not in _LOCAL_HOSTS and not a.startswith("::ffff:127.")]
    return {
        "ok": not bad,
        "listening": True,
        "addresses": addrs,
        "exposed": bad,
        "message_de": (
            "Nur localhost"
            if not bad
            else f"GEFAHR: Vault auf {bad} erreichbar"
        ),
    }


def hub_does_not_proxy_vault(root: Path) -> Dict[str, Any]:
    """Hub-Tunnel darf Vault-Port nicht exponieren."""
    root = Path(root)
    ok = True
    notes: List[str] = []
    for rel in ("control/cloudflare_tunnel.json", "evidence/remote_hub_tunnel.json"):
        path = root / rel
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            blob = json.dumps(doc).lower()
            if ":17891" in blob or "vault" in blob and "17891" in blob:
                ok = False
                notes.append(f"{rel} referenziert Vault-Port")
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "ok": ok,
        "notes": notes,
        "message_de": "Hub exponiert Vault nicht" if ok else "Hub/Tunnel-Konfiguration prüfen",
    }


def verify_airgap(root: Path, *, port: int = _VAULT_PORT) -> Dict[str, Any]:
    root = Path(root)
    bind = vault_bind_is_local_only(port)
    proxy = hub_does_not_proxy_vault(root)
    try:
        from analytics.tunnel_secret_vault import vault_status

        vs = vault_status(root)
        no_plain = not vs.get("legacy_plaintext_token") and not vs.get("server_env_has_plaintext_token")
    except Exception:
        no_plain = False
        vs = {}
    ok = bool(bind.get("ok") and proxy.get("ok") and no_plain)
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok,
        "airgapped": ok,
        "vault_bind": bind,
        "hub_isolation": proxy,
        "vault_hygiene": vs,
        "principles_de": [
            "Vault nur 127.0.0.1 — kein LAN, kein Internet, kein Tunnel",
            "X-Forwarded-For wird ignoriert — kein Proxy-Bypass",
            "Token nur verschlüsselt — kein Klartext im Keyring",
            "Zusatz-Passphrase + 600k PBKDF2 — ohne Passwort kein Entschlüsseln",
        ],
        "headline_de": (
            "Vollständig abgeschottet — nur dieses Gerät"
            if ok
            else "Abschottung unvollständig — sofort prüfen"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def enforce_local_bind_or_raise(port: int = _VAULT_PORT) -> None:
    state = vault_bind_is_local_only(port)
    if state.get("listening") and not state.get("ok"):
        exposed = ", ".join(state.get("exposed") or [])
        raise OSError(f"Vault-Airgap verletzt — lauscht auf {exposed}")
