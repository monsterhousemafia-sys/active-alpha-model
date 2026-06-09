from __future__ import annotations

from pathlib import Path

import pandas as pd

from analytics.pilot_today_pick import BLOCKED_SYMBOLS, load_today_pick


def test_load_today_pick_from_portfolio(tmp_path: Path) -> None:
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "signal_date": ["2026-06-01", "2026-06-01"],
            "ticker": ["SPY", "INTC"],
            "target_weight": [0.1, 0.05],
            "alpha_lcb": [0.0, 0.03],
        }
    )
    df.to_csv(out / "latest_target_portfolio.csv", index=False)
    pick = load_today_pick(tmp_path)
    assert pick["symbol"] == "INTC"
    assert pick["executable"] is True


def test_sndk_not_in_blocked_symbols() -> None:
    assert "SNDK" not in BLOCKED_SYMBOLS


def test_load_today_pick_includes_sndk(tmp_path: Path) -> None:
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "signal_date": ["2026-06-01", "2026-06-01"],
            "ticker": ["SNDK", "INTC"],
            "target_weight": [0.08, 0.05],
            "alpha_lcb": [0.04, 0.03],
            "eligible": [True, True],
        }
    )
    df.to_csv(out / "latest_target_portfolio.csv", index=False)
    pick = load_today_pick(tmp_path)
    assert pick["symbol"] == "SNDK"
    assert pick["executable"] is True
