"""Linux operator scope — user-approved levels A–D for Auto on Ubuntu."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCOPE_REL = Path("control/linux_operator_scope.json")
_ACTIONS_REL = Path("evidence/linux_operator_actions.jsonl")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_operator_scope(root: Path) -> Dict[str, Any]:
    path = Path(root) / _SCOPE_REL
    if not path.is_file():
        return {"approved_levels": ["A"], "max_level": "A", "levels": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def approved_levels(root: Path) -> List[str]:
    return list(load_operator_scope(root).get("approved_levels") or [])


def level_allowed(root: Path, level: str) -> bool:
    level = str(level or "").upper().strip()
    order = ["A", "B", "C", "D"]
    max_level = str(load_operator_scope(root).get("max_level") or "A").upper()
    if level not in order:
        return False
    if level not in approved_levels(root):
        return False
    return order.index(level) <= order.index(max_level) if max_level in order else False


def level_autonomous(root: Path, level: str) -> bool:
    if not level_allowed(root, level):
        return False
    levels = load_operator_scope(root).get("levels") or {}
    block = levels.get(str(level).upper()) or {}
    return bool(block.get("autonomous"))


def log_operator_action(
    root: Path,
    *,
    level: str,
    action: str,
    result: str,
    approved: bool = True,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    root = Path(root)
    path = root / _ACTIONS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at_utc": _utc_now(),
        "level": str(level).upper(),
        "action": action,
        "result": result,
        "approved": approved,
        "agent": load_operator_scope(root).get("agent_name") or "Auto",
        "details": details or {},
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    try:
        from analytics.operator_public_status import publish_public_status

        publish_public_status(root, notify=False)
    except Exception:
        pass
    try:
        from analytics.operator_visibility import notify_desktop_if_available

        if level in ("B", "C", "D") or action in ("monday_checklist", "h1_watch", "learn", "maintain"):
            notify_desktop_if_available(
                f"Active Alpha · {level}",
                f"{action}: {result}"[:160],
            )
    except Exception:
        pass


def scope_summary_de(root: Path) -> Dict[str, Any]:
    cfg = load_operator_scope(root)
    levels = cfg.get("levels") or {}
    lines = []
    for key in ("A", "B", "C", "D"):
        block = levels.get(key) or {}
        if not block:
            continue
        ok = level_allowed(root, key)
        auto = level_autonomous(root, key) if ok else False
        mark = "✓" if ok else "✗"
        mode = "autonom" if auto else ("mit Freigabe" if ok else "—")
        lines.append(f"{mark} {key} {block.get('label_de', key)} ({mode})")
    return {
        "approved_levels": approved_levels(root),
        "max_level": cfg.get("max_level"),
        "approved_at_utc": cfg.get("approved_at_utc"),
        "summary_lines_de": lines,
        "always_forbidden": list(cfg.get("always_forbidden") or []),
    }
