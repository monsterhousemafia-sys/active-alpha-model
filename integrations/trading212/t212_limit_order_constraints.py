"""T212 limit-order constraints — min quantity probe + cash utilization."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from integrations.trading212.t212_order_error_parser import extract_min_quantity, is_min_quantity_error

_CACHE_REL = Path("live_pilot/manual_execution/readonly_real_account_state/limit_order_constraints.json")

# Use full verified free cash for sizing; broker may still reject oversize orders.
T212_MAX_CASH_UTILIZATION = 1.0
US_EQUITY_RESERVATION_BUFFER = 1.0


def _cache_path(root: Path) -> Path:
    return Path(root) / _CACHE_REL


def _load_cache(root: Path) -> Dict[str, Any]:
    path = _cache_path(root)
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(root: Path, doc: Dict[str, Any]) -> None:
    path = _cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def cached_min_quantity(root: Path, ticker: str) -> Optional[float]:
    key = str(ticker).upper()
    entry = (_load_cache(root).get("min_quantity_by_ticker") or {}).get(key)
    if entry is None:
        return None
    try:
        return float(entry)
    except (TypeError, ValueError):
        return None


def record_min_quantity(root: Path, ticker: str, min_qty: float) -> None:
    doc = _load_cache(root)
    by = dict(doc.get("min_quantity_by_ticker") or {})
    by[str(ticker).upper()] = round(float(min_qty), 8)
    doc["min_quantity_by_ticker"] = by
    _save_cache(root, doc)


def probe_min_quantity(
    root: Path,
    *,
    ticker: str,
    limit_price: float,
    use_cache: bool = True,
) -> Tuple[Optional[float], str]:
    """
    Discover broker min quantity via tiny probe (1 req). Returns (min_qty, status).
    """
    root = Path(root)
    ticker = str(ticker).upper()
    if use_cache:
        cached = cached_min_quantity(root, ticker)
        if cached is not None:
            return cached, "CACHE"

    if os.environ.get("AA_SKIP_MIN_QTY_PROBE", "").strip() == "1":
        return None, "PROBE_SKIPPED"

    from integrations.trading212.t212_confirmed_execution_client import (
        T212ConfirmedExecutionClient,
        T212ExecutionBlockedError,
    )
    from integrations.trading212.t212_order_pacing import acquire_limit_order_slot, record_limit_order_result

    body = {
        "ticker": ticker,
        "quantity": 0.001,
        "limitPrice": round(float(limit_price), 2),
        "timeValidity": "DAY",
    }
    acquire_limit_order_slot(root)
    client = T212ConfirmedExecutionClient.from_execution_profile(root)
    try:
        response = client.submit_limit_order(body, root=root)
        record_limit_order_result(root, success=True)
        order_id = response.get("id") if isinstance(response, dict) else None
        if order_id is not None:
            try:
                client.cancel_order(order_id, root=root)
            except T212ExecutionBlockedError:
                pass
        return None, "UNEXPECTED_OK"
    except T212ExecutionBlockedError as exc:
        record_limit_order_result(root, success=False, error=str(exc))
        if is_min_quantity_error(str(exc)):
            min_q = extract_min_quantity(str(exc))
            if min_q is not None:
                record_min_quantity(root, ticker, min_q)
                return min_q, "PROBE"
        return None, "PROBE_OTHER"
    finally:
        time.sleep(0.1)


def apply_min_quantity_floor(quantity: float, min_qty: Optional[float], *, headroom: float = 1.03) -> float:
    if min_qty is None or min_qty <= 0:
        return round(float(quantity), 4)
    floor = round(float(min_qty) * float(headroom), 4)
    return round(max(float(quantity), floor), 4)


def spendable_cash_eur(free_cash_eur: float | None, *, min_reserve_eur: float) -> float:
    if free_cash_eur is None:
        return 0.0
    raw = max(0.0, float(free_cash_eur) - float(min_reserve_eur))
    return max(0.0, raw * T212_MAX_CASH_UTILIZATION)
