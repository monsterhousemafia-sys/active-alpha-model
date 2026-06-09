"""Cash wave planner — pro-rata buy scaling."""
from __future__ import annotations

from execution.confirmed_live.rebalance_wave_planner import plan_allocation_wave, plan_rebalance_wave


def _buys(n: int, each: float) -> list:
    return [
        {"symbol": f"S{i}", "side": "BUY", "notional_eur": each}
        for i in range(n)
    ]


def test_wave_factor_one_when_cash_covers_sum() -> None:
    wave = plan_rebalance_wave(_buys(13, 470 / 13), 500.0)
    assert wave["scale_factor"] == 1.0
    assert abs(wave["total_buy_notional_scaled"] - 470.0) < 0.2
    assert wave["buy_count_scaled"] == 13


def test_wave_scales_down_when_cash_insufficient() -> None:
    wave = plan_rebalance_wave(_buys(13, 470 / 13), 200.0)
    assert wave["scale_factor"] < 0.45
    assert wave["total_buy_notional_scaled"] <= 200.01
    assert wave["total_buy_notional_scaled"] >= 199.0


def test_sells_unchanged() -> None:
    orders = [{"symbol": "OLD", "side": "SELL", "notional_eur": 50.0}] + _buys(2, 100.0)
    wave = plan_rebalance_wave(orders, 80.0)
    sells = [o for o in wave["orders"] if o["side"] == "SELL"]
    assert sells[0]["notional_eur"] == 50.0
    assert sum(o["notional_eur"] for o in wave["orders"] if o["side"] == "BUY") <= 80.01


def test_allocation_wave_maps_target_eur() -> None:
    rows = [{"symbol": "STX", "target_eur": 100.0}, {"symbol": "WDC", "target_eur": 100.0}]
    wave = plan_allocation_wave(rows, 120.0)
    assert len(wave["allocations"]) == 2
    assert sum(r["target_eur"] for r in wave["allocations"]) <= 120.01
