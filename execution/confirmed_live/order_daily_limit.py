"""Optional daily order submission counter — no cap enforced (unlimited)."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_STATE_REL = Path("live_pilot/confirmed_execution/daily_order_submissions.json")


def _today_key() -> str:
    return date.today().isoformat()


def _path(root: Path) -> Path:
    p = Path(root) / _STATE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_daily_submissions(root: Path) -> Dict[str, Any]:
    path = _path(root)
    if not path.is_file():
        return {"by_day": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"by_day": {}}
    except (json.JSONDecodeError, OSError):
        return {"by_day": {}}


def submissions_today(root: Path) -> int:
    doc = load_daily_submissions(root)
    return int((doc.get("by_day") or {}).get(_today_key()) or 0)


def max_orders_per_day(root: Path | None = None) -> Optional[int]:
    """
    Return daily cap from policy, or None for unlimited.
    0 or negative in policy means unlimited.
    """
    if root is None:
        return None
    try:
        from analytics.live_trading_operations import load_policy

        raw = load_policy(root).get("max_orders_per_day")
        if raw is None:
            return None
        cap = int(raw)
        return None if cap <= 0 else cap
    except Exception:
        return None


def can_submit_more_orders_today(root: Path) -> tuple[bool, str]:
    """Always allow unless policy sets a positive max_orders_per_day."""
    cap = max_orders_per_day(root)
    if cap is None:
        return True, ""
    n = submissions_today(root)
    if n >= cap:
        return False, f"MAX_ORDERS_PER_DAY_EXCEEDED ({n}/{cap})"
    return True, ""


def record_successful_submission(root: Path, *, draft_id: str | None = None) -> Dict[str, Any]:
    """Audit counter only — does not block further submissions."""
    doc = load_daily_submissions(root)
    by_day = dict(doc.get("by_day") or {})
    key = _today_key()
    by_day[key] = int(by_day.get(key) or 0) + 1
    doc["by_day"] = by_day
    doc["last_submission_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if draft_id:
        doc["last_draft_id"] = draft_id
    atomic_write_json(_path(root), doc)
    return doc
