from __future__ import annotations

from pathlib import Path

import pandas as pd

import active_alpha_model as aam
from aa_universe import save_universe_snapshot


def test_diy_pit_universe_keeps_top_n_per_date():
    dates = pd.bdate_range("2024-01-01", periods=5)
    rows = []
    adv_map = {"A": 100e6, "B": 90e6, "C": 80e6, "D": 70e6, "E": 60e6}
    for dt in dates:
        for tk, adv in adv_map.items():
            rows.append(
                {
                    "date": pd.Timestamp(dt),
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
    for dt in dates:
        day = out[out["date"] == pd.Timestamp(dt)]
        assert int(day["in_universe"].sum()) == 2
        top = day.loc[day["in_universe"], "ticker"].tolist()
        assert top == ["A", "B"]


def test_static_universe_keeps_all_rows():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "ticker": ["A", "B"],
            "universe_adv": [1e6, 2e6],
            "close": [10.0, 20.0],
            "universe_history_days": [300, 300],
        }
    )
    cfg = aam.BacktestConfig(universe_mode="static", membership_mode="off")
    out = aam.apply_universe_filter(df, cfg)
    assert bool(out["in_universe"].all())
    assert (out["universe_reason"] == "static").all()


def test_membership_filter_blocks_future_tickers(tmp_path):
    membership = tmp_path / "ticker_membership.csv"
    pd.DataFrame(
        [
            {"ticker": "OLD", "valid_from": "2020-01-01", "valid_to": "", "source": "test", "reason": "old"},
            {"ticker": "NEW", "valid_from": "2026-01-01", "valid_to": "", "source": "test", "reason": "future"},
        ]
    ).to_csv(membership, index=False)
    features = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-01", "2026-02-01"]),
            "ticker": ["OLD", "NEW", "NEW"],
            "in_universe": [True, True, True],
            "universe_reason": ["test", "test", "test"],
        }
    )
    cfg = aam.BacktestConfig(membership_file=str(membership), membership_mode="strict", runtime_mode="backtest")
    filtered = aam.apply_membership_filter_to_features(features, cfg)
    assert bool(filtered.loc[(filtered["ticker"] == "OLD") & (filtered["date"] == pd.Timestamp("2025-01-01")), "in_universe"].iloc[0])
    assert not bool(filtered.loc[(filtered["ticker"] == "NEW") & (filtered["date"] == pd.Timestamp("2025-01-01")), "in_universe"].iloc[0])
    assert bool(filtered.loc[(filtered["ticker"] == "NEW") & (filtered["date"] == pd.Timestamp("2026-02-01")), "in_universe"].iloc[0])


def test_universe_snapshot_includes_sector_gics_columns(tmp_path: Path) -> None:
    records = [
        {
            "ticker": "AAPL",
            "source_symbol": "AAPL",
            "company": "Apple Inc.",
            "sector_gics": "Information Technology",
            "sector_coarse": "Technology",
            "source": "wikipedia_sp500",
        }
    ]
    cache = tmp_path / "universe_snapshots"
    path = save_universe_snapshot(records, cache, source_detail="s6_test")
    df = pd.read_csv(path)
    assert "sector_gics" in df.columns
    assert "sector_coarse" in df.columns
    assert df.iloc[0]["sector_gics"] == "Information Technology"
    latest = pd.read_csv(cache / "sp500_latest.csv")
    assert "sector_gics" in latest.columns
