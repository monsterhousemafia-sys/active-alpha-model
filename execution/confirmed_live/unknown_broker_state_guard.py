"""Unknown broker state — no auto-retry."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

UNKNOWN_STATE = "FAILED_UNKNOWN_BROKER_STATE_RECONCILIATION_REQUIRED"


def _store_path(root: Path) -> Path:
    p = root / "live_pilot/confirmed_execution/unknown_broker_states.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def register_unknown(root: Path, *, draft_id: str, context: str) -> Dict[str, Any]:
    path = _store_path(root)
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"entries": []}
    entry = {
        "draft_id": draft_id,
        "context": context,
        "status": UNKNOWN_STATE,
        "registered_at_utc": _utc_now(),
        "auto_retry_allowed": False,
    }
    data.setdefault("entries", []).append(entry)
    atomic_write_json(path, data)
    return entry


def has_open_unknown_for_instrument(root: Path, instrument: str) -> bool:
    path = _store_path(root)
    if not path.is_file():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    sym = instrument.upper()
    for e in data.get("entries") or []:
        if e.get("status") == UNKNOWN_STATE and str(e.get("instrument", "")).upper() == sym:
            return True
    return False


def blocks_submission(root: Path, *, instrument: Optional[str] = None) -> bool:
    path = _store_path(root)
    if not path.is_file():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    for e in data.get("entries") or []:
        if e.get("status") != UNKNOWN_STATE:
            continue
        if instrument is None or str(e.get("instrument", "")).upper() == instrument.upper():
            return True
    return False
