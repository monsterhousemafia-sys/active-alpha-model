"""Live-Trading dashboard — Paper-parity workflow (mark / rebalance / signal)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.live_trading_dashboard.window import LiveTradingDashboardWindow

__all__ = ["LiveTradingDashboardWindow"]


def __getattr__(name: str):
    if name == "LiveTradingDashboardWindow":
        from ui.live_trading_dashboard.window import LiveTradingDashboardWindow

        return LiveTradingDashboardWindow
    raise AttributeError(name)
