"""Tests for P16H confirmed order workflow."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from execution.confirmed_live.confirmed_execution_mode_controller import (
    ACTIVATION_PHRASE,
    activate_by_user,
    can_submit_orders,
    is_active,
)
from execution.confirmed_live.global_kill_switch import activate as kill_on, is_active as kill_active
from execution.confirmed_live.managed_scope_service import create_baseline, set_managed_scope
from execution.confirmed_live.order_confirmation_token_service import confirmation_phrase, issue_token, validate_and_consume
from execution.confirmed_live.order_draft_service import create_draft, refresh_draft_status
from execution.confirmed_live.order_preflight_gate import run_preflight
from execution.confirmed_live.order_submission_service import submit_confirmed_order
from integrations.trading212.t212_confirmed_execution_client import T212ConfirmedExecutionClient, T212ExecutionBlockedError
from integrations.trading212.t212_execution_endpoint_registry import BLOCKED_LIVE_ORDER_TYPES
from research.p16h.p16g_import_verification import EXPECTED_P16G_ZIP_SHA256, verify_p16g_import


@pytest.fixture(autouse=True)
def _p16h_tests_without_p17_review_lock(monkeypatch) -> None:
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "0")


@pytest.fixture(autouse=True)
def _block_live_submission(monkeypatch):
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "1")
    monkeypatch.setenv("AA_EXECUTION_DRY_RUN", "1")


def test_p16g_import_verification():
    root = Path(__file__).resolve().parents[1]
    if not (root / "outgoing_cursor_observation/p16g_interactive_desktop_product").is_dir():
        pytest.skip("P16G package not present")
    res = verify_p16g_import(root)
    assert res.get("gui_stack_present") is True
    assert res.get("readonly_clients_present") is True


def test_core_live_locked_by_default(tmp_path: Path) -> None:
    assert not is_active(tmp_path)
    assert not can_submit_orders(tmp_path)


def test_core_live_activation_phrase(tmp_path: Path) -> None:
    bad = activate_by_user(tmp_path, phrase="wrong", risk_ack=True)
    assert not bad.get("ok")
    good = activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    assert good.get("ok")
    assert is_active(tmp_path)


def test_core_live_activation_phrase_normalizes_dashes(tmp_path: Path) -> None:
    from execution.confirmed_live.confirmed_execution_mode_controller import activation_phrase_matches

    assert activation_phrase_matches(ACTIVATION_PHRASE.replace("-", "\u2013"))
    variant = "  " + ACTIVATION_PHRASE + "  "
    assert activation_phrase_matches(variant)


def test_core_live_guard_pilot_with_review_on(tmp_path: Path, monkeypatch) -> None:
    from execution.confirmed_live.pilot_live_trading_policy import enable_pilot_live_trading, activation_phrase

    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    enable_pilot_live_trading(
        tmp_path,
        phrase=activation_phrase(),
        risk_ack=True,
    )
    good = activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    assert good.get("ok")


def test_kill_switch_blocks_submit(tmp_path: Path) -> None:
    activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    kill_on(tmp_path)
    assert kill_active(tmp_path)
    assert not can_submit_orders(tmp_path)


def test_confirmation_token_one_time(tmp_path: Path) -> None:
    payload = {"instrument": "OXY", "side": "BUY", "max_notional_eur": 50.0, "limit_price": 50.0, "quantity": 1, "order_type": "LIMIT_BUY", "t212_instrument_id": "OXY_US_EQ"}
    issued = issue_token(tmp_path, payload, profile="T212_PROFILE_CONFIRMED_EXECUTION")
    token = issued["one_time_token"]
    v1 = validate_and_consume(tmp_path, token, payload)
    assert v1.get("valid")
    v2 = validate_and_consume(tmp_path, token, payload)
    assert not v2.get("valid")


def test_payload_change_invalidates_token(tmp_path: Path) -> None:
    payload = {"instrument": "OXY", "side": "BUY", "max_notional_eur": 50.0, "limit_price": 50.0, "quantity": 1, "order_type": "LIMIT_BUY", "t212_instrument_id": "OXY_US_EQ"}
    issued = issue_token(tmp_path, payload, profile="X")
    changed = {**payload, "max_notional_eur": 51.0}
    v = validate_and_consume(tmp_path, issued["one_time_token"], changed)
    assert v.get("error") == "INVALIDATED_PAYLOAD_CHANGED_REVIEW_REQUIRED_AGAIN"


def test_preflight_blocks_without_baseline(tmp_path: Path) -> None:
    draft = {"instrument": "OXY", "side": "BUY", "max_notional_eur": 50, "order_type": "LIMIT_BUY", "limit_price": 50, "t212_instrument_id": "OXY_US_EQ"}
    pf = run_preflight(tmp_path, draft, readonly_cash=500.0, account_currency="EUR")
    assert not pf.get("passed")
    assert "MANAGED_LIVE_PILOT_BASELINE_REQUIRED" in pf.get("blockers", [])


def test_preflight_blocks_non_eur(tmp_path: Path) -> None:
    create_baseline(tmp_path, account_currency="USD", available_cash=500, positions=[])
    set_managed_scope(tmp_path, managed_instruments=["OXY"])
    activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    draft = {"instrument": "OXY", "side": "BUY", "max_notional_eur": 50, "order_type": "LIMIT_BUY", "limit_price": 50, "t212_instrument_id": "OXY_US_EQ"}
    pf = run_preflight(tmp_path, draft, readonly_cash=500.0, account_currency="USD")
    assert "BLOCKED_ACCOUNT_CURRENCY_POLICY_REQUIRED" in pf.get("blockers", [])


def test_dry_run_submission_after_confirmation(tmp_path: Path) -> None:
    from integrations.trading212.t212_auth_profile_model import PROFILE_CONFIRMED_EXECUTION
    from integrations.trading212.t212_dual_profile_credential_store import set_profile_credentials

    set_profile_credentials(PROFILE_CONFIRMED_EXECUTION, api_key="test-key", api_secret="test-secret", mode="LIVE")
    create_baseline(tmp_path, account_currency="EUR", available_cash=500, positions=[])
    set_managed_scope(tmp_path, managed_instruments=["OXY"])
    activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    draft = create_draft(tmp_path, instrument="OXY", side="BUY", max_notional_eur=50, limit_price=50, t212_id="OXY_US_EQ", quantity=1)
    refresh_draft_status(tmp_path, draft, readonly_cash=500, account_currency="EUR")
    issued = issue_token(tmp_path, draft, profile="X")
    result = submit_confirmed_order(tmp_path, draft, one_time_token=issued["one_time_token"], readonly_cash=500, account_currency="EUR", dry_run=True)
    assert result.get("ok")


def test_execution_client_blocked_in_smoke(monkeypatch) -> None:
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "1")
    from integrations.trading212.t212_credentials_loader import T212Credentials

    client = T212ConfirmedExecutionClient(T212Credentials("k", "s"))
    with pytest.raises(T212ExecutionBlockedError):
        client.submit_limit_order({"ticker": "X", "quantity": 1, "limitPrice": 1})


def test_market_orders_blocked_in_registry() -> None:
    assert "MARKET" in BLOCKED_LIVE_ORDER_TYPES


def test_interactive_nav_count(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow, NAV_ITEMS

    QApplication.instance() or QApplication([])
    win = InteractiveCockpitWindow(tmp_path)
    assert win.stack.count() == len(NAV_ITEMS)
    assert win.verify_no_order_buttons() is True


def test_confirmation_phrase_format() -> None:
    p = confirmation_phrase({"side": "BUY", "instrument": "OXY", "max_notional_eur": 50.0})
    assert "OXY" in p and "50.00" in p
