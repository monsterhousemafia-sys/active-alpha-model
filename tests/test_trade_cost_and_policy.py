from __future__ import annotations

import active_alpha_model as aam


def test_trading212_fee_model():
    buy = aam.estimate_backtest_trade_cost(
        1000.0,
        10.0,
        "BUY",
        aam.BacktestConfig(fee_model="trading212_us", slippage_bps=2.0, trading212_fx_bps=15.0),
    )
    sell = aam.estimate_backtest_trade_cost(
        1000.0,
        10.0,
        "SELL",
        aam.BacktestConfig(fee_model="trading212_us", slippage_bps=2.0, trading212_fx_bps=15.0),
    )
    assert abs(float(buy["commission"])) < 1e-12
    assert buy["fx_fee"] > 0 and buy["slippage"] > 0
    assert sell["sec_fee"] > 0 and sell["finra_taf"] > 0


def test_capital_curve_policy_ordering():
    curve_small = aam.choose_capital_curve_policy(1000.0, fee_model="trading212_us", policy="balanced")
    curve_large = aam.choose_capital_curve_policy(100000.0, fee_model="trading212_us", policy="balanced")
    assert curve_small.rebalance_every >= curve_large.rebalance_every
    assert curve_small.top_k < curve_large.top_k
    assert curve_small.max_position > curve_large.max_position
    assert (curve_small.min_trade_value / curve_small.capital) >= (curve_large.min_trade_value / curve_large.capital)
    assert curve_small.min_trade_value < curve_small.capital * curve_small.max_position


def test_phase_timings_roundtrip():
    timings = aam.PhaseTimings()
    timings.set("unit_test", 0.5)
    assert timings.as_dict()["sections_seconds"]["unit_test"] == 0.5
