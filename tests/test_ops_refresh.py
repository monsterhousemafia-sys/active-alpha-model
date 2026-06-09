"""Tests for periodic operational data refresh."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from aa_ops_refresh import (
    ops_refresh_due,
    read_ops_meta,
    run_ops_refresh,
    write_ops_meta,
)


def test_ops_refresh_due_without_meta():
    assert ops_refresh_due({}, interval_hours=24)


def test_ops_refresh_not_due_after_recent_success():
    meta = {"last_success_at_utc": datetime.now(timezone.utc).isoformat()}
    assert not ops_refresh_due(meta, interval_hours=24)


def test_write_and_read_ops_meta(tmp_path: Path):
    write_ops_meta(tmp_path, {"ok": True, "price_latest": "2026-05-29"})
    meta = read_ops_meta(tmp_path)
    assert meta["ok"] is True
    assert meta["price_latest"] == "2026-05-29"
    assert "updated_at_utc" in meta


def test_run_ops_refresh_skips_when_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "model_out"
    out.mkdir()
    cache = out / "price_cache"
    cache.mkdir()
    pd.DataFrame({"date": ["2026-05-29"], "close": [100.0]}).to_parquet(cache / "ohlcv_panel.parquet", index=False)
    (cache / "price_cache_meta.json").write_text(
        json.dumps({"created_at_utc": "2099-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    pd.DataFrame({"ticker": ["AAPL"], "signal_date": ["2026-05-29"]}).to_csv(
        out / "latest_target_portfolio.csv", index=False
    )
    write_ops_meta(out, {"last_success_at_utc": datetime.now(timezone.utc).isoformat()})
    env = {
        "AA_BACKTEST_OUT_DIR": str(out),
        "AA_PRICE_CACHE_TTL_HOURS": "24",
        "AA_AUTO_OPS_REFRESH": "1",
    }
    monkeypatch.setattr("aa_data_freshness.last_expected_market_date", lambda **_: date(2026, 5, 29))
    monkeypatch.setattr("aa_features._price_cache_is_fresh", lambda meta, ttl: True)
    logs: list[str] = []

    result = run_ops_refresh(tmp_path, env, log=logs.append, include_signal=False)
    assert result.skipped
    assert any("übersprungen" in line for line in logs)


def test_run_ops_refresh_forces_download_env_when_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "model_out"
    out.mkdir()
    env = {
        "AA_BACKTEST_OUT_DIR": str(out),
        "AA_SKIP_DOWNLOAD_IF_CACHED": "1",
        "AA_AUTO_OPS_REFRESH": "1",
        "AA_BACKTEST_TICKER_SOURCE": "sp500_pit",
        "AA_MEMBERSHIP_FILE": "ticker_membership.csv",
    }
    monkeypatch.setattr("aa_data_freshness.last_expected_market_date", lambda **_: date(2026, 5, 29))
    monkeypatch.setattr("aa_ops_refresh.refresh_price_panel_with_retry", lambda *a, **k: True)
    monkeypatch.setattr("aa_ops_refresh.refresh_universe_if_needed", lambda *a, **k: False)
    logs: list[str] = []

    result = run_ops_refresh(tmp_path, env, log=logs.append, force=True, include_signal=False)
    assert result.prices_refreshed
    assert result.env_updates.get("AA_FORCE_REBUILD_FEATURES") == "1"
    assert result.env_updates.get("AA_SKIP_DOWNLOAD_IF_CACHED") == "1"


def test_run_ops_refresh_records_sector_reference_refreshed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aa_data_freshness import DailyDataReport, last_expected_market_date

    out = tmp_path / "model_out"
    out.mkdir()
    env = {
        "AA_BACKTEST_OUT_DIR": str(out),
        "AA_AUTO_OPS_REFRESH": "1",
        "AA_SKIP_DOWNLOAD_IF_CACHED": "0",
    }
    ref = last_expected_market_date()
    monkeypatch.setattr("aa_ops_refresh.refresh_price_panel_with_retry", lambda *a, **k: True)
    monkeypatch.setattr("aa_ops_refresh.refresh_universe_if_needed", lambda *a, **k: False)
    monkeypatch.setattr(
        "aa_sector_reference.ensure_sector_reference_fresh",
        lambda *a, **k: {"refreshed": True, "message_de": "Sektoren OK"},
    )
    monkeypatch.setattr(
        "aa_ops_refresh.assess_daily_data",
        lambda *a, **k: DailyDataReport(
            reference_date=ref,
            price_current=True,
            signal_current=True,
            ok=True,
        ),
    )
    run_ops_refresh(tmp_path, env, log=lambda _: None, force=True, include_signal=False)
    meta = read_ops_meta(out)
    assert meta.get("sector_reference_refreshed") is True
