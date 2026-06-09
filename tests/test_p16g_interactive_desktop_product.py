"""Tests for P16G interactive desktop cockpit."""
from __future__ import annotations

from pathlib import Path

import pytest

from integrations.trading212.t212_official_endpoint_registry import READONLY_GET_PATHS, official_api_snapshot
from integrations.trading212.t212_query_policy import is_blocked_order_path
from integrations.trading212.t212_request_allowlist import validate_method
from ui.interactive_cockpit.services.scenario_planning_service import calculate_scenario, parse_amount_input


def test_history_orders_not_blocked_as_live_orders() -> None:
    assert is_blocked_order_path("/equity/history/orders") is False
    assert is_blocked_order_path("/equity/orders") is True
    assert is_blocked_order_path("/equity/orders/limit") is True


def test_write_methods_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_method("POST", "/equity/account/summary")


def test_official_readonly_paths_include_history() -> None:
    snap = official_api_snapshot()
    assert "/equity/history/orders" in snap["readonly_get_paths"]
    assert "/equity/history/orders" in READONLY_GET_PATHS


def test_scenario_decimal_comma() -> None:
    v, err = parse_amount_input("123,45")
    assert err is None
    assert v == 123.45


def test_scenario_budget_over_frame() -> None:
    calc = calculate_scenario(
        {"capital_eur": 500, "reserve_eur": 50, "items": [{"symbol": "OXY", "amount_eur": 500}]},
        authorized_capital=500,
    )
    assert calc["budget_gate"] == "FAIL"
    assert "ÜBER" in calc["planning_status"]


def test_scenario_no_auto_execution() -> None:
    calc = calculate_scenario({"capital_eur": 100, "reserve_eur": 10, "items": []})
    assert calc["automatic_execution"] is False


def test_interactive_window_smoke(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication
    from ui.interactive_cockpit.main_window import NAV_ITEMS, InteractiveCockpitWindow

    QApplication.instance() or QApplication([])
    win = InteractiveCockpitWindow(tmp_path)
    assert win.verify_no_order_buttons() is True
    assert win.stack.count() == len(NAV_ITEMS)


def test_credential_session_store() -> None:
    from integrations.trading212.t212_session_credential_store import (
        clear_session_credentials,
        get_session_credentials,
        set_session_credentials,
    )

    set_session_credentials(api_key="k", api_secret="s", mode="DEMO_READ_ONLY")
    creds = get_session_credentials()
    assert creds is not None and creds.configured
    clear_session_credentials()
    assert get_session_credentials() is None


def test_trigger_50_boundary() -> None:
    from intraday.trigger.realized_net_profit_trigger import evaluate_trigger_status

    assert evaluate_trigger_status(profit_eur=49.99, broker_connected=True, has_reconciled_trades=True) == (
        "INACTIVE_REALIZED_NET_PROFIT_BELOW_50_EUR"
    )
    assert evaluate_trigger_status(profit_eur=50.0, broker_connected=True, has_reconciled_trades=True) == (
        "TRIGGER_REACHED_INTRADAY_PAPER_BRANCH_UNLOCKED"
    )
