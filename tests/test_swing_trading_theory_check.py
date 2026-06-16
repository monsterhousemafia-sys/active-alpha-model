"""Swing trading theory daily check."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.swing_trading_theory_check import run_swing_trading_theory_check


def test_swing_check_with_portfolio(tmp_path) -> None:
    (tmp_path / "model_output_sp500_pit_t212/price_cache").mkdir(parents=True)
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control").mkdir()
    (tmp_path / "control/swing_trading_theory_policy.json").write_text(
        json.dumps({"min_uptrend_share": 0.5, "min_pullback_in_uptrend_today": 1}),
        encoding="utf-8",
    )
    import pandas as pd

    port = pd.DataFrame(
        [
            {
                "signal_date": "2026-06-09",
                "ticker": "AAA",
                "target_weight": 0.6,
                "mom_63_21": 0.2,
                "rev_5": -0.01,
                "trend_50": 1.0,
            },
            {
                "signal_date": "2026-06-09",
                "ticker": "BBB",
                "target_weight": 0.4,
                "mom_63_21": 0.1,
                "rev_5": 0.02,
                "trend_50": 1.0,
            },
        ]
    )
    port.to_csv(tmp_path / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False)
    dates = pd.date_range("2026-06-01", periods=10, freq="B")
    panel = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "ticker": ["AAA"] * 10 + ["BBB"] * 10,
            "Close": [100 + i * 0.5 for i in range(10)] + [50 - i * 0.1 for i in range(10)],
        }
    )
    panel.to_parquet(tmp_path / "model_output_sp500_pit_t212/price_cache/ohlcv_panel.parquet")
    doc = run_swing_trading_theory_check(tmp_path, persist=True)
    assert doc["ok"] is True
    assert doc["shows_today"] is True
    assert (tmp_path / "evidence/swing_trading_theory_latest.json").is_file()
