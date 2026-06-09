"""R3 Session-Manager — Sitzungszustand zwischen Login und Desktop."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_STATE_NAME = "r3_session_state.json"
_SHARE_REL = Path(".local/share/r3-os")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def state_path() -> Path:
    return Path.home() / _SHARE_REL / _STATE_NAME


def load_login_config(root: Path) -> Dict[str, Any]:
    path = Path(root) / "control/r3_login_shell.json"
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            return doc if isinstance(doc, dict) else {}
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "post_login_path": "/desktop",
        "login_path": "/login",
        "session_ttl_hours": 12,
        "require_login_before_desktop": True,
    }


def load_session_state() -> Dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _session_expired(doc: Dict[str, Any], *, ttl_hours: float) -> bool:
    started = str(doc.get("started_at_utc") or "")
    if not started:
        return True
    try:
        t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - t0).total_seconds() / 3600.0
        return age_h > float(ttl_hours)
    except (ValueError, TypeError):
        return True


def is_r3_session_active(root: Path | None = None) -> bool:
    root = Path(root or Path(__file__).resolve().parents[1])
    cfg = load_login_config(root)
    if not cfg.get("require_login_before_desktop", True):
        return True
    doc = load_session_state()
    if not doc.get("active"):
        return False
    user = str(os.environ.get("USER") or "")
    if user and doc.get("user") and str(doc.get("user")) != user:
        return False
    if _session_expired(doc, ttl_hours=float(cfg.get("session_ttl_hours") or 12)):
        return False
    return True


def ensure_native_session(root: Path) -> Dict[str, Any]:
    """Lokale R3-App: Sitzung setzen/erneuern (Cockpit darf /r3 ohne Login-Redirect)."""
    root = Path(root)
    if os.environ.get("R3_SESSION") != "1" and os.environ.get("R3_NATIVE_SHELL") != "1":
        return load_session_state()
    return mark_session_started(root)


def mark_session_started(root: Path, *, user: Optional[str] = None) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_login_config(root)
    user = str(user or os.environ.get("USER") or "operator")
    hostname = os.uname().nodename
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "active": True,
        "user": user,
        "hostname": hostname,
        "started_at_utc": _utc_now(),
        "post_login_path": str(cfg.get("post_login_path") or "/desktop"),
        "graphical": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        "headline_de": f"R3-Sitzung · {user}@{hostname}",
    }
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, doc)
    return doc


def end_session() -> Dict[str, Any]:
    path = state_path()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    return {"ok": True, "message_de": "R3-Sitzung beendet"}


def resolve_hub_entry_path(root: Path) -> str:
    """Login oder Desktop — je nach aktiver R3-Sitzung."""
    cfg = load_login_config(root)
    if is_r3_session_active(root):
        return str(cfg.get("post_login_path") or "/desktop")
    return str(cfg.get("login_path") or "/login")


def session_status_doc(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_login_config(root)
    state = load_session_state()
    active = is_r3_session_active(root)
    plane: Dict[str, Any] = {}
    try:
        from analytics.r3_system_plane import session_panel

        plane = session_panel(root)
    except Exception:
        pass
    return {
        "ok": True,
        "r3_session_active": active,
        "require_login": bool(cfg.get("require_login_before_desktop", True)),
        "entry_path": resolve_hub_entry_path(root),
        "state": state,
        "logind": plane,
        "headline_de": (
            str(state.get("headline_de") or plane.get("headline_de") or "R3 Session")
            if active
            else "Nicht angemeldet — Login erforderlich"
        ),
    }
