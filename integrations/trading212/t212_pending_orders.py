"""Read pending equity orders — reserve estimate for buy sizing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List


def _parse_orders_payload(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [o for o in raw if isinstance(o, dict)]
    if isinstance(raw, dict):
        items = raw.get("items") or raw.get("orders") or []
        if isinstance(items, list):
            return [o for o in items if isinstance(o, dict)]
    return []


def fetch_pending_equity_orders(root: Path) -> List[Dict[str, Any]]:
    """GET /api/v0/equity/orders — active orders only."""
    from integrations.trading212.t212_confirmed_execution_client import T212ConfirmedExecutionClient

    client = T212ConfirmedExecutionClient.from_execution_profile(root)
    raw = client.get_json("/equity/orders", root=root)
    return _parse_orders_payload(raw)


def pending_buy_reservation_eur(root: Path) -> float:
    """
    Rough EUR hold for open BUY orders (limit: qty * limitPrice; market: filledValue or 0).
    """
    total = 0.0
    try:
        orders = fetch_pending_equity_orders(root)
    except Exception:
        return 0.0
    for order in orders:
        side = str(order.get("side") or "").upper()
        if side and side != "BUY":
            continue
        status = str(order.get("status") or "").upper()
        if status in ("CANCELLED", "FILLED", "REJECTED"):
            continue
        qty = abs(float(order.get("quantity") or 0))
        if qty <= 0:
            continue
        lim = float(order.get("limitPrice") or order.get("limit_price") or 0)
        if lim > 0:
            total += qty * lim
            continue
        filled = float(order.get("filledValue") or order.get("value") or 0)
        if filled > 0:
            total += filled
    return round(total, 2)
