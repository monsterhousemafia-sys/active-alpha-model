from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from aa_features import _merge_ohlcv_panels, merge_recent_ohlcv_into_price_cache


def test_merge_ohlcv_panels_keeps_latest_per_ticker_day():
    existing = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-05-28", "2026-05-29"]),
            "ticker": ["SPY", "SPY"],
            "Close": [100.0, 101.0],
        }
    )
    incoming = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-05-29", "2026-06-01"]),
            "ticker": ["SPY", "SPY"],
            "Close": [999.0, 102.0],
        }
    )
    merged = _merge_ohlcv_panels(existing, incoming)
    spy = merged[merged["ticker"] == "SPY"].sort_values("date")
    assert float(spy.iloc[-1]["Close"]) == 102.0
    assert len(spy) == 3


def test_merge_recent_ohlcv_into_price_cache_updates_spy(tmp_path: Path, monkeypatch):
    cache = tmp_path / "price_cache"
    cache.mkdir()
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-05-29"]),
            "ticker": ["SPY"],
            "Open": [1.0],
            "High": [1.0],
            "Low": [1.0],
            "Close": [1.0],
            "Volume": [1],
        }
    ).to_parquet(cache / "ohlcv_panel.parquet", index=False)

    import yfinance as yf

    idx = pd.to_datetime(["2026-05-30", "2026-06-01"])
    frame = pd.DataFrame(
        {
            ("SPY", "Open"): [2.0, 3.0],
            ("SPY", "High"): [2.0, 3.0],
            ("SPY", "Low"): [2.0, 3.0],
            ("SPY", "Close"): [2.0, 3.0],
            ("SPY", "Volume"): [10, 20],
        },
        index=idx,
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)

    monkeypatch.setattr(yf, "download", lambda *a, **k: frame)

    latest = merge_recent_ohlcv_into_price_cache(cache, ["SPY"], lookback_days=14)
    assert latest == date(2026, 6, 1)
    panel = pd.read_parquet(cache / "ohlcv_panel.parquet")
    assert pd.to_datetime(panel["date"]).max().date() == date(2026, 6, 1)
