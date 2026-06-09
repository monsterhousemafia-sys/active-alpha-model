"""Fail-closed runtime guard — pause on critical incidents."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json


def _path(root: Path) -> Path:
    p = root / "live_pilot/confirmed_execution/fail_closed_runtime_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_state(root: Path) -> Dict[str, Any]:
    path = _path(root)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "NORMAL", "incidents": []}


def is_paused(root: Path) -> bool:
    return load_state(root).get("status") == "PAUSED_FAIL_CLOSED_REQUIRES_USER_REVIEW"


def pause_fail_closed(root: Path, *, reason: str, category: str = "RUNTIME") -> Dict[str, Any]:
    st = load_state(root)
    incident = {"timestamp_utc": _utc_now(), "category": category, "reason": reason}
    st["status"] = "PAUSED_FAIL_CLOSED_REQUIRES_USER_REVIEW"
    st.setdefault("incidents", []).append(incident)
    atomic_write_json(_path(root), st)
    return st


def clear_after_user_review(root: Path) -> Dict[str, Any]:
    st = {"status": "NORMAL", "cleared_at_utc": _utc_now(), "incidents": load_state(root).get("incidents", [])}
    atomic_write_json(_path(root), st)
    return st


def active_incidents(root: Path) -> List[Dict[str, Any]]:
    st = load_state(root)
    if st.get("status") != "PAUSED_FAIL_CLOSED_REQUIRES_USER_REVIEW":
        return []
    return list(st.get("incidents") or [])
