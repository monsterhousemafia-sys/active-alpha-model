"""Load saved EXE setup permission questionnaire (user choices for future app configuration)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

QUESTIONNAIRE_REL = Path("control") / "exe_setup_permissions_questionnaire.json"


def questionnaire_path(root: Path) -> Path:
    return Path(root) / QUESTIONNAIRE_REL


def load_exe_setup_permissions(root: Path) -> Optional[Dict[str, Any]]:
    path = questionnaire_path(root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def selected_response(root: Path, question_id: str) -> Optional[Dict[str, Any]]:
    doc = load_exe_setup_permissions(root)
    if not doc:
        return None
    for item in doc.get("responses") or []:
        if str(item.get("id")) == question_id:
            return item
    return None


def setup_pending(root: Path) -> bool:
    doc = load_exe_setup_permissions(root)
    if not doc:
        return False
    impl = doc.get("implementation_status") or {}
    return not bool(impl.get("applied_to_runtime"))
