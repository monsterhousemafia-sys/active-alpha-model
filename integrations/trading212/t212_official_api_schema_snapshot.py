"""Official API schema snapshot metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def api_schema_snapshot() -> Dict[str, Any]:
    return {
        "source": "https://docs.trading212.com/api",
        "openapi_reference": "Trading 212 Public API v0",
        "fetched_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "demo_base_url": "https://demo.trading212.com/api/v0",
        "live_base_url_blocked": True,
        "write_methods_blocked": True,
        "order_endpoints_blocked": True,
    }
