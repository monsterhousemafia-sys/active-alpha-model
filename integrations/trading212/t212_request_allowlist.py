"""Exact GET-only allowlist for Trading 212 demo read-only sync."""
from __future__ import annotations

from typing import FrozenSet
from urllib.parse import urlparse

from integrations.trading212.t212_environment_guard import assert_demo_url, normalize_demo_path
from integrations.trading212.t212_query_policy import is_blocked_order_path, validate_query_for_path

ALLOWED_GET_PATHS: FrozenSet[str] = frozenset(
    {
        "/equity/account/summary",
        "/equity/account/cash",
        "/equity/positions",
        "/equity/metadata/instruments",
        "/equity/metadata/exchanges",
        "/equity/history/orders",
        "/equity/history/transactions",
        "/equity/history/dividends",
    }
)

ORDER_PATH_FRAGMENTS: FrozenSet[str] = frozenset(
    {
        "/equity/orders",
        "/orders",
        "/order/",
        "/pies",
        "/exports",
    }
)


def _normalized_path(path: str) -> str:
    query = ""
    if path.startswith("http"):
        assert_demo_url(path.split("?", 1)[0])
        parsed = urlparse(path)
        base = parsed.path
        query = parsed.query
    else:
        if "?" in path:
            base, query = path.split("?", 1)
        else:
            base = normalize_demo_path(path)
    validate_query_for_path(base, query)
    return base.split("?", 1)[0].rstrip("/") or base.split("?", 1)[0]


def validate_get_path(path: str) -> None:
    normalized = _normalized_path(path)
    if is_blocked_order_path(normalized):
        raise PermissionError(f"TRADING212_ORDER_ENDPOINT_BLOCKED:{normalized}")
    if normalized not in ALLOWED_GET_PATHS:
        raise PermissionError(f"TRADING212_GET_NOT_ON_ALLOWLIST:{normalized}")


def validate_method(method: str, path: str) -> None:
    m = method.upper()
    if m != "GET":
        raise PermissionError(f"TRADING212_WRITE_REQUEST_BLOCKED:{m}:{path}")
    validate_get_path(path)
