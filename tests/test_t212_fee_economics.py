from pathlib import Path

from integrations.trading212.t212_fee_economics import (
    estimate_round_trip_cost_eur,
    is_notional_worth_trading,
    net_buy_target_after_costs,
    trade_fee_hurdle_eur,
)


def test_round_trip_includes_fx_both_legs() -> None:
    est = estimate_round_trip_cost_eur(100.0)
    assert est["fx_cost_eur"] > 0
    assert est["round_trip_cost_eur"] > est["fx_cost_eur"]


def test_micro_trade_blocked() -> None:
    ok, reason = is_notional_worth_trading(5.0, None)
    assert not ok
    assert "Kostenhürde" in reason or "Gebühren" in reason or "Notional" in reason


def test_larger_trade_allowed() -> None:
    ok, _ = is_notional_worth_trading(200.0, None)
    assert ok


def test_net_buy_target_reduced(tmp_path: Path) -> None:
    adj = net_buy_target_after_costs(100.0, tmp_path)
    assert adj["net_target_eur"] < adj["gross_target_eur"]


def test_hurdle_scales_with_notional() -> None:
    small = trade_fee_hurdle_eur(None, notional_eur=20.0)
    large = trade_fee_hurdle_eur(None, notional_eur=500.0)
    assert large >= small
