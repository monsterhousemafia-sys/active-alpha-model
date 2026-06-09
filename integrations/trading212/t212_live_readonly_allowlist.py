"""GET-only allowlist for Trading 212 live read-only observation."""
from __future__ import annotations

from typing import FrozenSet
from urllib.parse import urlparse

from integrations.trading212.t212_live_readonly_guard import assert_live_readonly_url, normalize_live_path
from integrations.trading212.t212_query_policy import is_blocked_order_path, validate_query_for_path
from integrations.trading212.t212_request_allowlist import ORDER_PATH_FRAGMENTS

LIVE_ALLOWED_GET_PATHS: FrozenSet[str] = frozenset(
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


def _normalized_live_path(path: str) -> str:
    query = ""
    if path.startswith("http"):
        assert_live_readonly_url(path.split("?", 1)[0])
        parsed = urlparse(path)
        base = parsed.path
        query = parsed.query
    else:
        if "?" in path:
            base, query = path.split("?", 1)
        else:
            base = normalize_live_path(path)
    rel = base.split("/api/v0", 1)[-1] if "/api/v0" in base else base
    rel = rel if rel.startswith("/") else f"/{rel}"
    validate_query_for_path(rel, query)
    return rel.split("?", 1)[0].rstrip("/") or rel.split("?", 1)[0]


def validate_live_get_path(path: str) -> None:
    normalized = _normalized_live_path(path)
    if is_blocked_order_path(normalized):
        raise PermissionError(f"TRADING212_ORDER_ENDPOINT_BLOCKED:{normalized}")
    if normalized not in LIVE_ALLOWED_GET_PATHS:
        raise PermissionError(f"TRADING212_LIVE_GET_NOT_ON_ALLOWLIST:{normalized}")


def validate_live_method(method: str, path: str) -> None:
    if method.upper() != "GET":
        raise PermissionError(f"TRADING212_WRITE_REQUEST_BLOCKED:{method}:{path}")
    validate_live_get_path(path)
