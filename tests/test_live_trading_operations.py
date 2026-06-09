from __future__ import annotations

from pathlib import Path

from analytics.live_trading_operations import (
    load_policy,
    rebalance_status,
    record_daily_mark,
)
from execution.confirmed_live.live_trading_enablement import (
    disable_live_trading,
    enable_live_trading,
    is_live_trading_enabled,
)


def test_live_trading_policy_and_mark_counter(tmp_path: Path) -> None:
    pol = load_policy(tmp_path)
    assert pol.get("enabled") is True
    assert pol.get("relaxed_order_preflight") is True
    assert pol.get("order_execution_type") == "limit"
    m1 = record_daily_mark(tmp_path, pol=pol)
    assert m1.get("recorded") is True
    m2 = record_daily_mark(tmp_path, pol=pol)
    assert m2.get("recorded") is False
    st = rebalance_status(tmp_path, pol=pol)
    assert st.get("recorded_trading_days_since_rebalance") == 1


def test_enable_live_trading_no_phrase(tmp_path: Path) -> None:
    res = enable_live_trading(tmp_path, risk_ack=True, phrase="ignored")
    assert res["ok"] is True
    assert is_live_trading_enabled(tmp_path)
    off = disable_live_trading(tmp_path)
    assert off["ok"] is True
    assert not is_live_trading_enabled(tmp_path)


def test_load_policy_daily_alpha_turnover_damping(tmp_path: Path) -> None:
    import json

    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps(
            {
                "active_profile": "daily_alpha_h1",
                "rebalance": {"min_weight_gap_pct": 2.5},
                "budget": {"min_position_eur": 25.0},
            }
        ),
        encoding="utf-8",
    )
    pol = load_policy(tmp_path)
    assert pol["min_weight_gap_pct"] == 2.5
    assert pol["min_trade_eur"] >= 25.0
