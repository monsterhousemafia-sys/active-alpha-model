#!/usr/bin/env python3
"""Load explicit user phase authorization (fail-closed without file)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
GO_PATH = ROOT / "control" / "r0_migration" / "user_phase_go.json"


def load_user_go(root: Path | None = None) -> Dict[str, Any]:
    root = root or ROOT
    p = root / GO_PATH.relative_to(ROOT)
    if not p.is_file():
        return {"status": "MISSING", "active": False}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "INVALID", "active": False}
    active = str(doc.get("status", "")).upper() == "ACTIVE"
    return {**doc, "active": active}


def is_phase_user_authorized(root: Path, phase: str) -> bool:
    doc = load_user_go(root)
    if not doc.get("active"):
        return False
    authorized = doc.get("phases_authorized") or {}
    return str(phase).upper() in authorized or str(phase).upper() in {
        k.upper() for k in authorized.keys()
    }
