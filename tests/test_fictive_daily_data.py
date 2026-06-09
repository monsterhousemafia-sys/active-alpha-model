from __future__ import annotations

from datetime import date

import pandas as pd

from aa_fictive_daily_data import (
    generate_fictive_ohlcv,
    is_fictive_price_source,
    resolve_price_data_source,
    seed_fictive_daily_cache,
)


def test_resolve_price_data_source():
    assert resolve_price_data_source(env={"AA_PRICE_DATA_SOURCE": "fictive"}) == "fictive"
    assert resolve_price_data_source(env={"AA_PRICE_DATA_SOURCE": "internet"}) == "internet"
    assert is_fictive_price_source(env={"AA_PRICE_DATA_SOURCE": "mock"}) is True


def test_generate_fictive_ohlcv_through_today():
    df = generate_fictive_ohlcv("AAPL", "2012-01-01", end=date(2026, 5, 29))
    assert len(df) > 3000
    assert df.index.max().date() == date(2026, 5, 29)
    assert {"Open", "High", "Low", "Close", "Volume"}.issubset(df.columns)
    assert (df["Close"] > 0).all()


def test_generate_fictive_reproducible():
    a = generate_fictive_ohlcv("MSFT", "2020-01-01", end=date(2026, 5, 29))
    b = generate_fictive_ohlcv("MSFT", "2020-01-01", end=date(2026, 5, 29))
    pd.testing.assert_series_equal(a["Close"], b["Close"])


def test_seed_fictive_daily_cache(tmp_path, monkeypatch):
    out = tmp_path / "model_out"
    out.mkdir()
    env = {
        "AA_BACKTEST_OUT_DIR": str(out),
        "AA_BENCHMARK": "SPY",
        "AA_START_DATE": "2020-01-01",
        "AA_PRICE_DATA_SOURCE": "fictive",
        "AA_RANDOM_SEED": "42",
        "AA_SKIP_DOWNLOAD_IF_CACHED": "0",
    }

    import active_alpha_model as aam

    def _fake_from_args(_args):
        return aam.BacktestConfig(start="2020-01-01", benchmark="SPY", random_seed=42)

    monkeypatch.setattr("aa_config.BacktestConfig.from_args", _fake_from_args)
    monkeypatch.setattr("aa_config.parse_args", lambda: None)
    monkeypatch.setattr("aa_config_env.build_backtest_argv", lambda _e: ["prog"])

    doc = seed_fictive_daily_cache(tmp_path, env, ["SPY", "AAPL"], force=True)
    assert doc["ok"] is True
    assert (out / "price_cache" / "ohlcv_panel.parquet").is_file()
    meta = (out / "price_cache" / "price_cache_meta.json").read_text(encoding="utf-8")
    assert "fictive" in meta
