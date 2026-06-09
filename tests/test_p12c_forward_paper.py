"""P12C forward paper trading tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.p12c.forward_runner import run_forward_paper_evaluation
from research.p12c.prospective_filter import filter_prospective_observations
from research.p12c.timestamp_chain import read_timestamp_chain


def test_p12c_prospective_filter_no_lookahead() -> None:
    quotes = pd.DataFrame(
        [
            {
                "ticker": "SPY",
                "last": 100.0,
                "received_at_utc": "2026-06-01T12:00:00+00:00",
                "market_event_time_utc": "2026-06-01T11:59:00+00:00",
            },
            {
                "ticker": "AAPL",
                "last": 150.0,
                "received_at_utc": "2026-05-31T12:00:00+00:00",
                "market_event_time_utc": "2026-05-31T12:00:00+00:00",
            },
        ]
    )
    eligible, rejected = filter_prospective_observations(quotes, observation_start_utc="2026-06-01T10:00:00+00:00")
    assert len(eligible) == 1
    assert eligible.iloc[0]["ticker"] == "SPY"
    assert any(r.get("reason") == "before_forward_window" for r in rejected)


def test_p12c_forward_evaluation(tmp_path: Path) -> None:
    out = run_forward_paper_evaluation(tmp_path)
    assert out["paper_trading_status"] == "COMPLETED_EVALUATION_WINDOW"
    assert out["lookahead_verified"] is True
    assert out["simulation_only"] is True
    assert out["evaluation"]["initial_capital_eur"] == 500.0


def test_p12c_timestamp_chain(tmp_path: Path) -> None:
    run_forward_paper_evaluation(tmp_path)
    chain = read_timestamp_chain(tmp_path)
    assert len(chain) >= 1
    assert chain[-1].get("broker_order_sent") is False


def test_p12c_no_broker_routing(tmp_path: Path) -> None:
    out = run_forward_paper_evaluation(tmp_path)
    assert out["broker_order_sent"] is False
    assert out["real_money"] is False
