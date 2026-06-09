"""Revenue-funded product and agent expansion roadmap."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ROADMAP_REL = Path("control") / "ROADMAP_REVENUE_FUNDED_EXPANSION.json"


def roadmap_path(root: Path) -> Path:
    return Path(root) / ROADMAP_REL


def load_revenue_expansion_roadmap(root: Path) -> Optional[Dict[str, Any]]:
    path = roadmap_path(root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def current_phase(root: Path) -> Optional[Dict[str, Any]]:
    doc = load_revenue_expansion_roadmap(root) or {}
    for phase in doc.get("phases") or []:
        if phase.get("status") == "COMPLETE":
            continue
        if phase.get("status") == "NOT_STARTED_BLOCKED_BY_GOVERNANCE":
            continue
        return phase
    phases = doc.get("phases") or []
    return phases[-1] if phases else None


def next_immediate_actions(root: Path) -> List[Dict[str, Any]]:
    doc = load_revenue_expansion_roadmap(root) or {}
    return list(doc.get("immediate_next_actions") or [])
