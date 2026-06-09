"""Tunnel-Steuerung — Quick/Token-Tunnel über remote_hub_access."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_PAUSE_REL = Path("evidence/tunnel_paused.json")


def is_tunnel_paused(root: Path) -> bool:
    from analytics.remote_hub_access import is_tunnel_paused as _paused

    return _paused(root)


def tunnel_control_status(root: Path) -> Dict[str, Any]:
    from analytics.remote_hub_access import load_tunnel_token, remote_access_status

    st = remote_access_status(root)
    token = bool(load_tunnel_token(root))
    paused = is_tunnel_paused(root)
    return {
        "ok": True,
        "paused": paused,
        "tunnel_stable": bool(st.get("tunnel_stable")),
        "tunnel_pid_alive": bool(st.get("tunnel_pid_alive")),
        "tunnel_token_set": token,
        "public_base_url": st.get("public_base_url"),
        "remote_ready": bool(st.get("remote_ready")),
        "headline_de": (
            "Tunnel stabil — URL bleibt nach Neustart"
            if token and st.get("tunnel_stable")
            else (
                f"Quick-Tunnel aktiv — {st.get('public_base_url') or '—'}"
                if st.get("tunnel_pid_alive")
                else "Tunnel nicht aktiv — spread-remote oder tunnel-stable setup"
            )
        ),
        "message_de": st.get("message_de") or "—",
    }


def tunnel_control_try_apply(root: Path, *, silent: bool = False) -> bool:
    from analytics.remote_hub_access import ensure_remote_hub_url, load_tunnel_token

    root = Path(root)
    if is_tunnel_paused(root):
        return False
    mode = "cloudflared-token" if load_tunnel_token(root) else "auto"
    out = ensure_remote_hub_url(root, mode=mode)
    return bool(out.get("ok"))


def tunnel_control_setup(root: Path, *, wait_s: int = 0) -> Dict[str, Any]:
    from analytics.remote_hub_access import ensure_remote_hub_url, load_tunnel_token

    root = Path(root)
    _set_paused(root, False)
    mode = "cloudflared-token" if load_tunnel_token(root) else "auto"
    out = ensure_remote_hub_url(root, mode=mode)
    doc = tunnel_control_status(root)
    doc["setup_ok"] = bool(out.get("ok"))
    doc["setup_detail"] = out
    return doc


def _set_paused(root: Path, paused: bool, *, reason_de: str = "") -> None:
    atomic_write_json(
        Path(root) / _PAUSE_REL,
        {"paused": paused, "reason_de": reason_de},
    )


def stop_all_tunnels(root: Path, *, reason_de: str = "") -> Dict[str, Any]:
    from analytics.remote_hub_access import stop_cloudflared_tunnel

    _set_paused(root, True, reason_de=reason_de or "manuell gestoppt")
    doc = stop_cloudflared_tunnel(root)
    doc["paused"] = True
    doc["message_de"] = reason_de or "Tunnel pausiert"
    return doc


def resume_tunnels(root: Path) -> Dict[str, Any]:
    from analytics.remote_hub_access import ensure_remote_hub_url

    root = Path(root)
    _set_paused(root, False)
    out = ensure_remote_hub_url(root, mode="auto")
    doc = tunnel_control_status(root)
    doc["resume_ok"] = bool(out.get("ok"))
    doc["resume_detail"] = out
    if not out.get("ok"):
        doc["message_de"] = str(out.get("message_de") or "Resume fehlgeschlagen")
    return doc
