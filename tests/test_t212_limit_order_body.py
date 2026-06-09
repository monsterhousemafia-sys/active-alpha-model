"""T212 limit order payload matches official API schema."""
from __future__ import annotations

from pathlib import Path

from execution.confirmed_live.order_submission_service import build_limit_order_body


def test_limit_order_body_uses_day_for_pilot_policy(tmp_path: Path) -> None:
    from analytics.pilot_day_trading_policy import save_unified_policy, load_unified_policy

    pol = load_unified_policy(tmp_path)
    pol["live_trading"] = {**(pol.get("live_trading") or {}), "limit_time_validity": "DAY"}
    save_unified_policy(tmp_path, pol)
    body = build_limit_order_body(
        {
            "side": "BUY",
            "quantity": 0.88,
            "limit_price": 93.97,
            "t212_instrument_id": "INTC_US_EQ",
        },
        root=tmp_path,
    )
    assert body["ticker"] == "INTC_US_EQ"
    assert body["quantity"] == 0.88
    assert body["limitPrice"] == 93.97
    assert body["timeValidity"] == "DAY"


def test_sell_order_negative_quantity() -> None:
    body = build_limit_order_body(
        {
            "side": "SELL",
            "quantity": 1.5,
            "limit_price": 10.0,
            "t212_instrument_id": "OXY_US_EQ",
        }
    )
    assert body["quantity"] == -1.5
