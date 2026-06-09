from execution.confirmed_live.order_sizing import (
    is_insufficient_funds_error,
    plan_executable_buy_order,
    shrink_quantity_for_retry,
)
from integrations.trading212.t212_user_messages import format_scaled_order_notice


def test_insufficient_detection() -> None:
    assert is_insufficient_funds_error("HTTP 400: insufficient-free-for-stocks-buy")
    assert not is_insufficient_funds_error("HTTP 401")


def test_plan_scales_down_when_cash_tight() -> None:
    plan = plan_executable_buy_order(
        target_notional_eur=82.0,
        limit_price_eur=94.0,
        free_cash_eur=70.0,
    )
    assert plan["scaled_down"] is True
    assert plan["executable_notional_eur"] < 82.0
    assert plan["quantity"] >= 0.01


def test_shrink_quantity_on_retry() -> None:
    assert shrink_quantity_for_retry(0.88, attempt=1) < 0.88


def test_scaled_notice_mentions_plan_vs_executed() -> None:
    msg = format_scaled_order_notice(
        symbol="INTC",
        target_notional_eur=82.0,
        executed_notional_eur=40.0,
        quantity=0.43,
        limit_price_eur=94.0,
        scaled_down=True,
        attempt_count=2,
    )
    assert "ℹ" in msg
    assert "82" in msg
    assert "40" in msg
