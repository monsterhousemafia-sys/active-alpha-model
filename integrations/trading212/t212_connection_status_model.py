"""Trading 212 connection status model for GUI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BrokerConnectionStatus:
    status: str = "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI"
    connection_name: str = "Trading 212"
    environment: str = "NONE"
    credentials_configured: bool = False
    last_successful_sync_utc: Optional[str] = None
    last_error: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    write_methods_blocked: bool = True
    order_endpoints_blocked: bool = True
    account_summary: Dict[str, Any] = field(default_factory=dict)
    cash_eur: Optional[float] = None
    cash_breakdown: Dict[str, Any] = field(default_factory=dict)
    positions_count: int = 0
    positions: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "connection_name": self.connection_name,
            "environment": self.environment,
            "credentials_configured": self.credentials_configured,
            "last_successful_sync_utc": self.last_successful_sync_utc,
            "last_error": self.last_error,
            "rate_limit_remaining": self.rate_limit_remaining,
            "write_methods_blocked": self.write_methods_blocked,
            "order_endpoints_blocked": self.order_endpoints_blocked,
            "cash_eur": self.cash_eur,
            "cash_breakdown": self.cash_breakdown,
            "positions_count": self.positions_count,
            "positions": self.positions,
            "account_summary": self.account_summary,
        }
