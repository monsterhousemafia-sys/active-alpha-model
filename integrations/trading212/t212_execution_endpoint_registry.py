"""Confirmed execution endpoints — from official API snapshot only."""
from __future__ import annotations

from typing import FrozenSet

# Official: POST /api/v0/equity/orders/limit — P16H live scope
CONFIRMED_LIVE_POST_PATHS: FrozenSet[str] = frozenset({
    "/equity/orders/limit",
    "/equity/orders/market",
})

# Official: DELETE /api/v0/equity/orders/{id} — cancel after user confirmation
CONFIRMED_CANCEL_METHOD = "DELETE"
CONFIRMED_CANCEL_PATH_PREFIX = "/equity/orders/"

LIVE_ORDER_TYPES_P16H = frozenset(
    {"LIMIT_BUY", "LIMIT_SELL_COVERED", "MARKET_BUY", "MARKET_SELL_COVERED"}
)

BLOCKED_LIVE_ORDER_TYPES = frozenset(
    {"MARKET", "STOP", "STOP_LIMIT", "SHORT", "LEVERAGE", "CFD", "UNCOVERED_SELL"}
)
