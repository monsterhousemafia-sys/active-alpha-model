"""Endpoint-specific query parameter policy for Trading 212 demo read-only."""
from __future__ import annotations

from typing import Dict, FrozenSet
from urllib.parse import parse_qs

ALLOWED_QUERY_BY_PATH: Dict[str, FrozenSet[str]] = {
    "/equity/metadata/instruments": frozenset(),
    "/equity/metadata/exchanges": frozenset(),
    "/equity/account/summary": frozenset(),
    "/equity/account/cash": frozenset(),
    "/equity/positions": frozenset(),
    "/equity/history/orders": frozenset({"limit", "cursor"}),
    "/equity/history/transactions": frozenset({"limit", "cursor"}),
    "/equity/history/dividends": frozenset({"limit", "cursor"}),
}


def is_blocked_order_path(normalized: str) -> bool:
    """Block live order routes but allow /equity/history/* read-only paths."""
    if normalized.startswith("/equity/history/"):
        return normalized == "/equity/history/exports"
    if normalized == "/equity/orders" or normalized.startswith("/equity/orders/"):
        return True
    if normalized.startswith("/equity/pies"):
        return True
    if "/exports" in normalized and not normalized.startswith("/equity/history/"):
        return True
    return False


def validate_query_for_path(path: str, query: str) -> None:
    normalized = path.split("?", 1)[0]
    if "?" in path:
        query = path.split("?", 1)[1]
    if not query:
        return
    allowed = ALLOWED_QUERY_BY_PATH.get(normalized)
    if allowed is None:
        raise PermissionError(f"TRADING212_UNKNOWN_PATH_FOR_QUERY:{normalized}")
    params = parse_qs(query.lstrip("?"), keep_blank_values=True)
    unknown = set(params) - set(allowed)
    if unknown:
        raise PermissionError(f"TRADING212_UNKNOWN_QUERY_PARAMS:{sorted(unknown)}")
