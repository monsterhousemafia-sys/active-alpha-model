from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from aa_live_daily_sync import (
    merge_ticker_universe,
    needs_between_trading_day_refresh,
    read_exemplar_portfolio_tickers,
)


def test_merge_ticker_universe_deduplicates():
    merged = merge_ticker_universe(["SPY", "AAPL"], ["aapl", "MSFT"], ["SPY"])
    assert merged == ["AAPL", "MSFT", "SPY"]


def test_read_exemplar_portfolio_tickers_from_fixture(tmp_path: Path):
    out = tmp_path / "model_out"
    out.mkdir()
    (out / "latest_target_portfolio.csv").write_text(
        "signal_date,ticker,target_weight,sector,correlation_cluster\n"
        "2026-05-29,SPY,0.2,Benchmark,Benchmark_Completion\n"
        "2026-05-29,AAA,0.5,Tech,TechCluster\n"
        "2026-05-29,BBB,0.3,Health,HealthCluster\n",
        encoding="utf-8",
    )
    tickers = read_exemplar_portfolio_tickers(out)
    assert tickers == ["AAA", "BBB"]


def test_needs_between_trading_day_refresh_when_synced_yesterday(tmp_path: Path, monkeypatch):
    out = tmp_path / "model_out"
    cache = out / "price_cache"
    cache.mkdir(parents=True)
    pd.DataFrame({"date": ["2026-06-01"], "ticker": ["SPY"], "Close": [1.0]}).to_parquet(
        cache / "ohlcv_panel.parquet", index=False
    )
    (cache / "price_cache_meta.json").write_text('{"created_at_utc": "2099-01-01T00:00:00+00:00"}', encoding="utf-8")
    (out / "latest_target_portfolio.csv").write_text(
        "signal_date,ticker\n2026-06-01,SPY\n", encoding="utf-8"
    )
    (out / "live_daily_sync.json").write_text(
        '{"synced_at_utc": "2026-06-01T08:00:00+00:00"}', encoding="utf-8"
    )
    env = {"AA_BACKTEST_OUT_DIR": str(out), "AA_PRICE_CACHE_TTL_HOURS": "24"}
    monkeypatch.setattr("aa_data_freshness.last_expected_market_date", lambda **_: date(2026, 6, 2))
    monkeypatch.setattr("aa_features._price_cache_is_fresh", lambda meta, ttl: True)

    assert needs_between_trading_day_refresh(tmp_path, env)
