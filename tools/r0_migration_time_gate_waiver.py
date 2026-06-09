"""Time-gate waiver for accelerated R0 migration track B."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

WAIVER_PATH = Path("control/r0_migration/migration_time_gate_waiver.json")


def load_waiver(root: Path) -> Optional[Dict[str, Any]]:
    p = root / WAIVER_PATH
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def waiver_active(root: Path) -> bool:
    data = load_waiver(root)
    return bool(data) and str(data.get("status", "")).upper() == "ACTIVE"


def waiver_track(root: Path) -> str:
    data = load_waiver(root) or {}
    return str(data.get("track") or "")
