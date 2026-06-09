"""Walk-forward mirror — daily mark + 5-day rebalance cadence."""
from __future__ import annotations

from pathlib import Path

import pytest

from analytics.pilot_walkforward_mirror import (
    build_rebalance_orders,
    load_state,
    rebalance_status,
    record_daily_mark,
    save_state,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "live_pilot/confirmed_execution").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_rebalance_due_after_five_marks(root: Path) -> None:
    save_state(
        root,
        {
            "mark_dates": ["2026-06-01"] * 4,
            "recorded_trading_days_since_rebalance": 4,
            "last_rebalance_date": "",
        },
    )
    st = rebalance_status(root)
    assert st["is_due"] is False
    assert st["days_remaining"] == 1

    record_daily_mark(root)
    st2 = rebalance_status(root)
    assert st2["recorded_trading_days_since_rebalance"] == 5
    assert st2["is_due"] is True
    assert st2["recommendation"] == "REBALANCE_DUE"


def test_build_rebalance_orders_sells_first() -> None:
    reeval = {
        "recommended_actions": [
            {"symbol": "AMD", "action_code": "NACHKAUF", "gap_eur": 40.0, "priority_score": 10, "weight_gap_pct": 5},
            {"symbol": "INTC", "action_code": "REDUZIEREN", "gap_eur": -30.0, "priority_score": 20, "weight_gap_pct": -4},
        ]
    }
    broker = {"positions": [], "cash_eur": 500}
    pol = {"min_trade_eur": 12.0, "min_weight_gap_pct": 0.5}
    orders = build_rebalance_orders(Path("."), broker=broker, reevaluation=reeval, pol=pol)
    assert len(orders) == 2
    assert orders[0]["side"] == "SELL"
    assert orders[0]["symbol"] == "INTC"
    assert orders[1]["side"] == "BUY"
