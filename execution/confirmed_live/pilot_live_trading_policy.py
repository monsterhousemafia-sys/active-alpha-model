"""Deprecated shim — use execution.confirmed_live.live_trading_enablement."""
from __future__ import annotations

from execution.confirmed_live.live_trading_enablement import (
    ack_path,
    activation_phrase,
    disable_live_trading,
    disable_pilot_live_trading,
    enable_live_trading,
    enable_pilot_live_trading,
    ensure_live_trading_enabled,
    is_live_trading_enabled,
    is_pilot_live_trading_enabled,
    live_submission_allowed,
    load_live_trading_ack,
    load_pilot_trading_ack,
)

__all__ = [
    "ack_path",
    "activation_phrase",
    "disable_live_trading",
    "disable_pilot_live_trading",
    "enable_live_trading",
    "enable_pilot_live_trading",
    "ensure_live_trading_enabled",
    "is_live_trading_enabled",
    "is_pilot_live_trading_enabled",
    "live_submission_allowed",
    "load_live_trading_ack",
    "load_pilot_trading_ack",
]
