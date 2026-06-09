"""Launch Live-Trading Invest UI — Paper-parity workflow on Trading 212."""
from __future__ import annotations

from aa_pilot_launch import (  # noqa: F401
    bootstrap_pilot_runtime,
    launch_default_pilot_ui,
    launch_ui,
    main,
    run_preflight,
)

bootstrap_live_trading_runtime = bootstrap_pilot_runtime
launch_live_trading_ui = launch_ui
launch_default_live_trading_ui = launch_default_pilot_ui

__all__ = [
    "bootstrap_live_trading_runtime",
    "bootstrap_pilot_runtime",
    "launch_default_live_trading_ui",
    "launch_default_pilot_ui",
    "launch_live_trading_ui",
    "launch_ui",
    "main",
    "run_preflight",
]
