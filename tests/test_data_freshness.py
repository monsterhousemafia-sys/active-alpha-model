"""Tests for daily data freshness checks at launcher startup."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from aa_data_freshness import (
    apply_stale_data_env,
    assess_daily_data,
    is_market_data_current,
    is_signal_current,
    last_expected_market_date,
    read_price_cache_latest_date,
    read_signal_date,
    verify_and_log_daily_data,
)


def test_last_expected_market_date_skips_weekend():
    assert last_expected_market_date(today=date(2026, 5, 31)) == date(2026, 5, 29)


def test_is_market_data_current_allows_recent_session():
    ref = date(2026, 5, 29)
    assert is_market_data_current(date(2026, 5, 29), reference=ref)
    assert is_market_data_current(date(2026, 5, 28), reference=ref)
    assert not is_market_data_current(date(2026, 5, 20), reference=ref)


def test_is_signal_current_within_week():
    ref = date(2026, 5, 29)
    assert is_signal_current(date(2026, 5, 29), reference=ref)
    assert is_signal_current(date(2026, 5, 22), reference=ref)
    assert not is_signal_current(date(2026, 5, 1), reference=ref)


def test_read_price_cache_latest_date(tmp_path: Path):
    cache = tmp_path / "price_cache"
    cache.mkdir()
    df = pd.DataFrame(
        {
            "date": ["2026-05-27", "2026-05-28", "2026-05-29"],
            "ticker": ["SPY", "SPY", "SPY"],
            "close": [1.0, 2.0, 3.0],
        }
    )
    df.to_parquet(cache / "ohlcv_panel.parquet", index=False)
    assert read_price_cache_latest_date(tmp_path) == date(2026, 5, 29)
    assert read_price_cache_latest_date(tmp_path, benchmark="SPY") == date(2026, 5, 29)


def test_read_price_cache_latest_date_benchmark_not_global_max(tmp_path: Path):
    cache = tmp_path / "price_cache"
    cache.mkdir()
    df = pd.DataFrame(
        {
            "date": ["2026-06-05", "2026-06-01", "2026-06-01"],
            "ticker": ["ILLQ", "SPY", "SPY"],
            "close": [1.0, 2.0, 3.0],
        }
    )
    df.to_parquet(cache / "ohlcv_panel.parquet", index=False)
    assert read_price_cache_latest_date(tmp_path, benchmark="SPY") == date(2026, 6, 1)
    assert read_price_cache_latest_date(tmp_path) == date(2026, 6, 5)


def test_read_signal_date(tmp_path: Path):
    df = pd.DataFrame({"ticker": ["AAPL"], "signal_date": ["2026-05-29"]})
    df.to_csv(tmp_path / "latest_target_portfolio.csv", index=False)
    assert read_signal_date(tmp_path) == date(2026, 5, 29)


def test_assess_daily_data_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "model_out"
    out.mkdir()
    cache = out / "price_cache"
    cache.mkdir()
    pd.DataFrame({"date": ["2026-05-29"], "close": [100.0]}).to_parquet(cache / "ohlcv_panel.parquet", index=False)
    meta = {"saved_at": "2099-01-01T00:00:00+00:00"}
    (cache / "price_cache_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    pd.DataFrame({"ticker": ["AAPL"], "signal_date": ["2026-05-29"]}).to_csv(
        out / "latest_target_portfolio.csv", index=False
    )
    env = {"AA_BACKTEST_OUT_DIR": str(out), "AA_PRICE_CACHE_TTL_HOURS": "24"}
    monkeypatch.setattr("aa_data_freshness.last_expected_market_date", lambda **_: date(2026, 5, 29))
    monkeypatch.setattr("aa_features._price_cache_is_fresh", lambda meta, ttl: True)

    report = assess_daily_data(tmp_path, env)
    assert report.ok
    assert report.price_current
    assert report.signal_current
    assert any("Tagesdaten gelesen und aktuell" in line for line in report.log_lines)


def test_assess_daily_data_stale_forces_refresh_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "model_out"
    out.mkdir()
    cache = out / "price_cache"
    cache.mkdir()
    old = (date(2026, 5, 29) - timedelta(days=10)).isoformat()
    pd.DataFrame({"date": [old], "close": [100.0]}).to_parquet(cache / "ohlcv_panel.parquet", index=False)
    (cache / "price_cache_meta.json").write_text(json.dumps({"saved_at": "2000-01-01"}), encoding="utf-8")
    pd.DataFrame({"ticker": ["AAPL"], "signal_date": ["2026-05-29"]}).to_csv(
        out / "latest_target_portfolio.csv", index=False
    )
    env = {"AA_BACKTEST_OUT_DIR": str(out), "AA_PRICE_CACHE_TTL_HOURS": "24", "AA_SKIP_DOWNLOAD_IF_CACHED": "1"}
    monkeypatch.setattr("aa_data_freshness.last_expected_market_date", lambda **_: date(2026, 5, 29))
    monkeypatch.setattr("aa_features._price_cache_is_fresh", lambda meta, ttl: False)

    report = assess_daily_data(tmp_path, env)
    assert not report.ok
    assert not report.price_current
    updated = apply_stale_data_env(env, report)
    assert updated["AA_SKIP_DOWNLOAD_IF_CACHED"] == "0"


def test_verify_and_log_daily_data_mutates_apply_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "model_out"
    out.mkdir()
    env = {"AA_BACKTEST_OUT_DIR": str(out), "AA_SKIP_DOWNLOAD_IF_CACHED": "1"}
    monkeypatch.setattr("aa_data_freshness.last_expected_market_date", lambda **_: date(2026, 5, 29))
    logs: list[str] = []

    report = verify_and_log_daily_data(tmp_path, env, log=logs.append, apply_env=env)
    assert not report.ok
    assert env["AA_SKIP_DOWNLOAD_IF_CACHED"] == "0"
    assert any(line.startswith("[INFO] Tagesdaten-Check") for line in logs)
