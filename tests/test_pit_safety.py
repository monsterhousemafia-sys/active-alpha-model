from __future__ import annotations

from pathlib import Path

import pandas as pd

import active_alpha_model as aam


def test_diy_pit_universe_is_date_local():
    """Later-day liquidity spikes must not retroactively change earlier universe membership."""
    rows = []
    for dt, adv_map in [
        (pd.Timestamp("2024-01-02"), {"A": 100e6, "B": 90e6, "C": 10e6}),
        (pd.Timestamp("2024-01-03"), {"A": 100e6, "B": 90e6, "C": 200e6}),
    ]:
        for tk, adv in adv_map.items():
            rows.append(
                {
                    "date": dt,
                    "ticker": tk,
                    "universe_adv": adv,
                    "close": 10.0,
                    "universe_history_days": 300,
                }
            )
    cfg = aam.BacktestConfig(
        universe_mode="diy_pit_liquidity",
        universe_top_n=2,
        top_k=2,
        universe_min_adv=10_000_000.0,
        universe_min_price=5.0,
        universe_min_history_days=252,
        membership_mode="off",
    )
    out = aam.apply_universe_filter(pd.DataFrame(rows), cfg)
    day1 = out[out["date"] == pd.Timestamp("2024-01-02")]
    assert set(day1.loc[day1["in_universe"], "ticker"]) == {"A", "B"}
    assert "C" not in set(day1.loc[day1["in_universe"], "ticker"])

    day2 = out[out["date"] == pd.Timestamp("2024-01-03")]
    assert set(day2.loc[day2["in_universe"], "ticker"]) == {"C", "A"}


def test_membership_valid_from_blocks_early_dates(tmp_path: Path):
    membership = tmp_path / "ticker_membership.csv"
    pd.DataFrame(
        [{"ticker": "NEW", "valid_from": "2024-06-01", "valid_to": "", "source": "test", "reason": "future"}]
    ).to_csv(membership, index=False)
    features = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-07-01"]),
            "ticker": ["NEW", "NEW"],
            "in_universe": [True, True],
            "universe_reason": ["test", "test"],
        }
    )
    cfg = aam.BacktestConfig(
        membership_file=str(membership),
        membership_mode="strict",
        runtime_mode="backtest",
    )
    filtered = aam.apply_membership_filter_to_features(features, cfg)
    early = filtered.loc[filtered["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    late = filtered.loc[filtered["date"] == pd.Timestamp("2024-07-01")].iloc[0]
    assert not bool(early["membership_allowed"])
    assert not bool(early["in_universe"])
    assert bool(late["membership_allowed"])
    assert bool(late["in_universe"])
    assert str(late["membership_valid_from"]) == "2024-06-01"
