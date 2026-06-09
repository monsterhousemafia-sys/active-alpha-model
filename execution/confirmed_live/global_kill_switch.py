"""Global kill switch — stops new submissions, does not auto-cancel."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _path(root: Path) -> Path:
    p = root / "live_pilot/confirmed_execution/kill_switch_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def is_active(root: Path) -> bool:
    path = _path(root)
    if not path.is_file():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("active"))
    except json.JSONDecodeError:
        return False


def activate(root: Path, *, reason: str = "USER_KILL_SWITCH") -> Dict[str, Any]:
    state = {"active": True, "reason": reason, "activated_at_utc": _utc_now()}
    atomic_write_json(_path(root), state)
    return state


def deactivate(root: Path) -> Dict[str, Any]:
    state = {"active": False, "deactivated_at_utc": _utc_now()}
    atomic_write_json(_path(root), state)
    return state


def load_state(root: Path) -> Dict[str, Any]:
    path = _path(root)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"active": False}
