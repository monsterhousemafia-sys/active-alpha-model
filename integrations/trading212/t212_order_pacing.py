"""T212 limit-order pacing — 1 POST / 2s; prevents user-facing HTTP 429 bursts."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from integrations.trading212.t212_sync_throttle import is_rate_limit_error
from integrations.trading212.t212_user_messages import humanize_t212_error

# Official limit: POST /equity/orders/limit → 1 req / 2s (per account).
MIN_LIMIT_ORDER_GAP_S = 2.6
# Market orders: up to 50 req/min — use a conservative 1.3s gap.
MIN_MARKET_ORDER_GAP_S = 1.3
ORDER_RATE_LIMIT_COOLDOWN_S = 90


def _throttle_path(root: Path) -> Path:
    return (
        Path(root)
        / "live_pilot/manual_execution/readonly_real_account_state/sync_throttle.json"
    )


def _read_doc(root: Path) -> dict:
    path = _throttle_path(root)
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_doc(root: Path, doc: dict) -> None:
    path = _throttle_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _parse_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def can_place_limit_order_now(root: Path) -> Tuple[bool, str]:
    """Pre-check before any order workflow (incl. auto-scale retries)."""
    doc = _read_doc(root)
    rl = _parse_utc(doc.get("last_order_rate_limit_utc"))
    if rl is not None:
        elapsed = (datetime.now(timezone.utc) - rl).total_seconds()
        if elapsed < ORDER_RATE_LIMIT_COOLDOWN_S:
            wait = int(ORDER_RATE_LIMIT_COOLDOWN_S - elapsed)
            return False, humanize_t212_error("429") + f"\nNächste Order in ca. {wait} s."
    return True, ""


def acquire_limit_order_slot(root: Path) -> None:
    """Block until T212 order rate window allows the next limit POST."""
    doc = _read_doc(root)
    last = _parse_utc(doc.get("last_limit_order_submit_utc"))
    if last is None:
        return
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    if elapsed < MIN_LIMIT_ORDER_GAP_S:
        time.sleep(MIN_LIMIT_ORDER_GAP_S - elapsed)


def record_limit_order_result(root: Path, *, success: bool, error: str = "") -> None:
    doc = _read_doc(root)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    doc["last_limit_order_submit_utc"] = now
    if success:
        doc.pop("last_order_rate_limit_utc", None)
    elif is_rate_limit_error(error):
        doc["last_order_rate_limit_utc"] = now
    _write_doc(root, doc)


def can_place_market_order_now(root: Path) -> Tuple[bool, str]:
    """Pre-check before market order workflow."""
    return can_place_limit_order_now(root)


def acquire_market_order_slot(root: Path) -> None:
    """Block until T212 market POST rate window allows the next request."""
    doc = _read_doc(root)
    last = _parse_utc(doc.get("last_market_order_submit_utc"))
    if last is None:
        return
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    if elapsed < MIN_MARKET_ORDER_GAP_S:
        time.sleep(MIN_MARKET_ORDER_GAP_S - elapsed)


def record_market_order_result(root: Path, *, success: bool, error: str = "") -> None:
    doc = _read_doc(root)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    doc["last_market_order_submit_utc"] = now
    doc["last_limit_order_submit_utc"] = now
    if success:
        doc.pop("last_order_rate_limit_utc", None)
    elif is_rate_limit_error(error):
        doc["last_order_rate_limit_utc"] = now
    _write_doc(root, doc)


def retry_delay_after_insufficient_funds() -> float:
    """Pause between auto-scale retries (same endpoint)."""
    return MIN_LIMIT_ORDER_GAP_S
