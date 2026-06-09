"""Regression tests for order execution hardening fixes."""
from __future__ import annotations

from pathlib import Path

import pytest

from analytics.live_trading_operations import normalize_execution_result
from execution.confirmed_live.order_daily_limit import (
    can_submit_more_orders_today,
    record_successful_submission,
    submissions_today,
)
from execution.confirmed_live.order_sizing import (
    MARKET_ORDER_SLIPPAGE_BUFFER,
    plan_executable_buy_order,
)
from execution.confirmed_live.order_preflight_gate import run_preflight
from execution.confirmed_live.managed_scope_service import create_baseline, set_managed_scope
from execution.confirmed_live.confirmed_execution_mode_controller import ACTIVATION_PHRASE, activate_by_user


def test_normalize_enqueue_only_marks_not_sent() -> None:
    out = normalize_execution_result(
        {
            "ok": True,
            "mode": "deferred_walkforward",
            "enqueued": 4,
            "executed": 0,
            "fallback": "enqueue_after_readiness_block",
            "message_de": "4 vorgemerkt",
        }
    )
    assert out.get("sent_to_t212") is False
    assert out.get("enqueue_only") is True
    assert out.get("ok") is False
    assert "Nicht an T212" in str(out.get("message_de") or "")


@pytest.fixture(autouse=True)
def _allow_core_live(monkeypatch) -> None:
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "0")


def test_daily_order_limit_unlimited_by_default(tmp_path: Path) -> None:
    create_baseline(tmp_path, account_currency="EUR", available_cash=500, positions=[])
    set_managed_scope(tmp_path, managed_instruments=["OXY"])
    activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    for _ in range(20):
        record_successful_submission(tmp_path, draft_id="x")
    assert submissions_today(tmp_path) == 20
    allowed, reason = can_submit_more_orders_today(tmp_path)
    assert allowed is True
    assert reason == ""
    draft = {
        "instrument": "OXY",
        "side": "BUY",
        "max_notional_eur": 40,
        "order_type": "LIMIT_BUY",
        "limit_price": 50,
        "t212_instrument_id": "OXY_US_EQ",
    }
    pf = run_preflight(tmp_path, draft, readonly_cash=500.0, account_currency="EUR")
    assert pf.get("passed")
    assert not any("MAX_ORDERS_PER_DAY" in b for b in pf.get("blockers") or [])


def test_sndk_preflight_not_identity_blocked(tmp_path: Path) -> None:
    create_baseline(tmp_path, account_currency="EUR", available_cash=500, positions=[])
    set_managed_scope(tmp_path, managed_instruments=["SNDK"])
    activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    draft = {
        "instrument": "SNDK",
        "side": "BUY",
        "max_notional_eur": 40,
        "order_type": "LIMIT_BUY",
        "limit_price": 1500.0,
        "t212_instrument_id": "SNDK_US_EQ",
    }
    pf = run_preflight(tmp_path, draft, readonly_cash=500.0, account_currency="EUR")
    blockers = pf.get("blockers") or []
    assert "INSTRUMENT_BLOCKED_AMBIGUOUS_OR_UNSUPPORTED" not in blockers
    assert pf.get("passed")


def test_market_sizing_no_extra_slippage_buffer() -> None:
    limit_plan = plan_executable_buy_order(
        target_notional_eur=100.0,
        limit_price_eur=100.0,
        free_cash_eur=200.0,
        execution_style="limit",
    )
    market_plan = plan_executable_buy_order(
        target_notional_eur=100.0,
        limit_price_eur=100.0,
        free_cash_eur=200.0,
        execution_style="market",
    )
    assert market_plan["quantity"] == limit_plan["quantity"]
    assert MARKET_ORDER_SLIPPAGE_BUFFER == 1.0
