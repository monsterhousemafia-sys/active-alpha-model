"""US day trading playbook coordinator."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from execution.confirmed_live.us_day_trading_coordinator import (
    build_day_trading_playbook,
    effective_full_refresh_ms,
    is_deferred_execution_allowed,
    load_policy,
)


def test_full_session_execution_allowed(tmp_path: Path) -> None:
    pol = load_policy(tmp_path)
    assert pol.get("execution_window_mode") == "full_session"
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": True, "phase": "OPEN"},
    ):
        assert is_deferred_execution_allowed(tmp_path) is True


def test_playbook_stale_quotes_action(tmp_path: Path) -> None:
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": True, "phase": "OPEN"},
    ):
        pb = build_day_trading_playbook(
            tmp_path,
            broker={"cash_eur": 100.0, "positions": []},
            plan={"primary_action": {"symbol": "INTC"}},
            champion_guard={"champion_ok": True, "signals_ok": True},
            reevaluation={"urgency": "STALE_QUOTES", "trade_required": False},
        )
    assert pb.get("next_action") == "REFRESH"


def test_open_early_faster_refresh_ms(tmp_path: Path) -> None:
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": True, "phase": "OPEN"},
    ):
        with patch(
            "analytics.pilot_day_trading_policy._session_detail_phase",
            return_value="OPEN_EARLY",
        ):
            ms = effective_full_refresh_ms(tmp_path)
    assert ms == 3 * 60 * 1000
