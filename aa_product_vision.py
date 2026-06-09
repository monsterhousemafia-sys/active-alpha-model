"""Load and query the saved professional EXE product vision (future roadmap)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

VISION_REL = Path("control") / "PRODUCT_VISION_PROFESSIONAL_EXE.json"


def vision_path(root: Path) -> Path:
    return Path(root) / VISION_REL


def load_product_vision(root: Path) -> Optional[Dict[str, Any]]:
    path = vision_path(root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def roadmap_phases(root: Path) -> List[Dict[str, Any]]:
    doc = load_product_vision(root) or {}
    return list(doc.get("roadmap_phases") or [])


def comparison_spec(root: Path) -> Dict[str, Any]:
    doc = load_product_vision(root) or {}
    return dict(doc.get("comparison_engine_spec") or {})


def onboarding_spec(root: Path) -> Dict[str, Any]:
    doc = load_product_vision(root) or {}
    return dict(doc.get("onboarding_questionnaire_spec") or {})
