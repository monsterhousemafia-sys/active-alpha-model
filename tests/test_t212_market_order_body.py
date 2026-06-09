"""T212 market order payload and preflight."""
from __future__ import annotations

from pathlib import Path

import pytest

from execution.confirmed_live.managed_scope_service import create_baseline, set_managed_scope
from execution.confirmed_live.confirmed_execution_mode_controller import ACTIVATION_PHRASE, activate_by_user
from execution.confirmed_live.order_draft_service import create_draft, refresh_draft_status
from execution.confirmed_live.order_preflight_gate import run_preflight
from execution.confirmed_live.order_submission_service import build_market_order_body, submit_confirmed_order
from execution.confirmed_live.order_execution_style import (
    resolve_order_execution_style,
    set_order_execution_style,
)


@pytest.fixture(autouse=True)
def _allow_core_live_activation(monkeypatch) -> None:
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "0")


def test_market_order_body_signed_quantity() -> None:
    buy = build_market_order_body(
        {"side": "BUY", "quantity": 1.25, "t212_instrument_id": "INTC_US_EQ"}
    )
    assert buy["ticker"] == "INTC_US_EQ"
    assert buy["quantity"] == 1.25
    assert buy["extendedHours"] is False
    sell = build_market_order_body(
        {"side": "SELL", "quantity": 2.0, "t212_instrument_id": "OXY_US_EQ"}
    )
    assert sell["quantity"] == -2.0


def test_market_draft_preflight_with_baseline(tmp_path: Path) -> None:
    create_baseline(tmp_path, account_currency="EUR", available_cash=500, positions=[])
    set_managed_scope(tmp_path, managed_instruments=["OXY"])
    activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    draft = create_draft(
        tmp_path,
        instrument="OXY",
        side="BUY",
        max_notional_eur=50,
        limit_price=50,
        t212_id="OXY_US_EQ",
        quantity=1,
        execution_style="market",
    )
    assert draft["order_type"] == "MARKET_BUY"
    draft = refresh_draft_status(tmp_path, draft, readonly_cash=500, account_currency="EUR")
    assert draft["status"] == "DRAFT_READY_FOR_REVIEW"


def test_order_execution_style_policy(tmp_path: Path) -> None:
    assert resolve_order_execution_style(tmp_path) == "limit"
    set_order_execution_style(tmp_path, "market")
    assert resolve_order_execution_style(tmp_path) == "market"
    set_order_execution_style(tmp_path, "limit")
    assert resolve_order_execution_style(tmp_path) == "limit"


def test_market_dry_run_submission(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "1")
    monkeypatch.setenv("AA_EXECUTION_DRY_RUN", "1")
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "0")
    from integrations.trading212.t212_auth_profile_model import PROFILE_CONFIRMED_EXECUTION
    from integrations.trading212.t212_dual_profile_credential_store import set_profile_credentials
    from execution.confirmed_live.order_confirmation_token_service import issue_token

    set_profile_credentials(PROFILE_CONFIRMED_EXECUTION, api_key="k", api_secret="s")
    create_baseline(tmp_path, account_currency="EUR", available_cash=500, positions=[])
    set_managed_scope(tmp_path, managed_instruments=["OXY"])
    activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    draft = create_draft(
        tmp_path,
        instrument="OXY",
        side="BUY",
        max_notional_eur=50,
        limit_price=50,
        t212_id="OXY_US_EQ",
        quantity=1,
        execution_style="market",
    )
    refresh_draft_status(tmp_path, draft, readonly_cash=500, account_currency="EUR")
    issued = issue_token(tmp_path, draft, profile="X")
    result = submit_confirmed_order(
        tmp_path,
        draft,
        one_time_token=issued["one_time_token"],
        readonly_cash=500,
        account_currency="EUR",
        dry_run=True,
        execution_style="market",
    )
    assert result.get("ok")
