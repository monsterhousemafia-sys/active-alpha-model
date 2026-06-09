"""Crash recovery — never auto-resubmit."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json


def _path(root: Path) -> Path:
    p = root / "live_pilot/confirmed_execution/recovery_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_recovery(root: Path) -> Dict[str, Any]:
    path = _path(root)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"pending_resubmit_allowed": False, "sessions": []}


def record_startup(root: Path, *, build_id: str = "P17") -> Dict[str, Any]:
    st = load_recovery(root)
    sessions = list(st.setdefault("sessions", []))
    sessions.append({"started_at_utc": _utc_now(), "build_id": build_id})
    st["sessions"] = sessions[-30:]
    st["pending_resubmit_allowed"] = False
    st["last_startup_utc"] = _utc_now()
    atomic_write_json(_path(root), st)
    return st


def crash_recovery_blocks_resubmit(root: Path) -> bool:
    """Always block automatic resubmit after crash or restart."""
    return True
