"""Official Trading 212 API endpoint classification — snapshot from docs.trading212.com."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List

DEMO_BASE_URL = "https://demo.trading212.com/api/v0"
LIVE_BASE_URL = "https://live.trading212.com/api/v0"
DOCS_SOURCE = "https://docs.trading212.com/api"
FETCHED_AT_UTC = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

READONLY_GET_PATHS: FrozenSet[str] = frozenset(
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

FORBIDDEN_WRITE_PREFIXES: FrozenSet[str] = frozenset(
    {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }
)

FORBIDDEN_ORDER_PATHS: FrozenSet[str] = frozenset(
    {
        "/equity/orders",
        "/equity/orders/limit",
        "/equity/orders/market",
        "/equity/orders/stop",
        "/equity/orders/stop_limit",
        "/equity/history/exports",
        "/equity/pies",
    }
)


def official_api_snapshot() -> Dict[str, Any]:
    return {
        "source": DOCS_SOURCE,
        "fetched_at_utc": FETCHED_AT_UTC,
        "demo_base_url": DEMO_BASE_URL,
        "live_base_url": LIVE_BASE_URL,
        "api_version": "v0",
        "beta": True,
        "auth": "HTTP Basic (API Key : API Secret)",
        "readonly_get_paths": sorted(READONLY_GET_PATHS),
        "forbidden_order_paths": sorted(FORBIDDEN_ORDER_PATHS),
        "write_methods_blocked": True,
        "pagination": {"limit_default": 20, "limit_max": 50, "cursor_based": True},
        "rate_limit_headers": [
            "x-ratelimit-limit",
            "x-ratelimit-period",
            "x-ratelimit-remaining",
            "x-ratelimit-reset",
            "x-ratelimit-used",
        ],
    }


def allowed_endpoints_json() -> Dict[str, Any]:
    return {
        "generated_at_utc": FETCHED_AT_UTC,
        "readonly_get_allowlist": sorted(READONLY_GET_PATHS),
        "blocked_write_methods": sorted(FORBIDDEN_WRITE_PREFIXES),
        "blocked_order_paths": sorted(FORBIDDEN_ORDER_PATHS),
    }
