"""Evolution governance gates — shared constants."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

GOVERNANCE_BLOCKED_ACTIONS = frozenset(
    {
        "auto_execute_us_open",
        "remove_gui_confirm_gate",
    }
)


def kernel_blocks_full_auto(root: Path) -> bool:
    path = Path(root) / "control/AI_KERNEL.json"
    if not path.is_file():
        return True
    try:
        kernel = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True
    safety = kernel.get("safety") or {}
    if safety.get("auto_execute_real_money"):
        return False
    return bool(safety.get("gui_confirm_required", True))
