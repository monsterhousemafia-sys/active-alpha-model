"""Legacy entry — redirects to the new Live-Trading dashboard."""
from __future__ import annotations

import sys
from pathlib import Path

from ui.live_trading_dashboard.window import LiveTradingDashboardWindow as MinimalInvestWindow


def launch_minimal_invest_app(root: Path | None = None) -> int:
    """Backward-compatible launcher alias for scripts/tests."""
    from aa_pilot_launch import launch_ui
    from aa_paths import project_root

    root = Path(root) if root is not None else project_root()
    return launch_ui(root)


__all__ = ["MinimalInvestWindow", "launch_minimal_invest_app"]
