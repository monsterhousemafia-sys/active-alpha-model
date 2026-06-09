"""FAILSAFE_MODE persistence and pipeline safety stops."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

FAILSAFE_FILE = "failsafe_state.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def failsafe_path(root: Path) -> Path:
    return Path(root) / "control" / FAILSAFE_FILE


def load_failsafe_state(root: Path) -> Dict[str, Any]:
    path = failsafe_path(root)
    if not path.is_file():
        return {"active": False, "pipeline_status": "IDLE", "critical_errors": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"active": True, "pipeline_status": "FAILSAFE_MODE", "critical_errors": ["failsafe_state_corrupt"]}


def is_failsafe_active(root: Path) -> bool:
    state = load_failsafe_state(root)
    return bool(state.get("active")) or str(state.get("pipeline_status", "")).upper() == "FAILSAFE_MODE"


def activate_failsafe(root: Path, *, reason: str, critical_errors: Optional[List[str]] = None) -> Path:
    payload = {
        "active": True,
        "pipeline_status": "FAILSAFE_MODE",
        "activated_at_utc": _utc_now(),
        "reason": reason,
        "critical_errors": list(critical_errors or [reason]),
    }
    return atomic_write_json(failsafe_path(root), payload)


def clear_failsafe(root: Path) -> Path:
    payload = {
        "active": False,
        "pipeline_status": "IDLE",
        "cleared_at_utc": _utc_now(),
        "critical_errors": [],
    }
    return atomic_write_json(failsafe_path(root), payload)


def pipeline_status_label(root: Path, *, job_running: bool = False) -> str:
    if is_failsafe_active(root):
        return "FAILSAFE_MODE"
    if job_running:
        return "RUNNING"
    return "IDLE"
