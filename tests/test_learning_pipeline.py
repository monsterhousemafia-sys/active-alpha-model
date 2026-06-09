"""Tests for live learning observation pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pandas as pd


def test_learning_policy_blocks_auto_training(tmp_path: Path):
    from market.learning_pipeline import ensure_learning_policy

    p = ensure_learning_policy(tmp_path)
    assert p["observation_collection_enabled"] is True
    assert p["auto_model_training_enabled"] is False
    assert p["auto_champion_update_enabled"] is False


def test_intraday_dedupe(tmp_path: Path):
    from market.learning_pipeline import append_intraday_from_snapshot, count_ledger_lines

    snap = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": "TEST",
        "executable_prices_eur": {"OXY": 71.0, "WDC": 80.0},
        "quotes_by_symbol": {},
        "freshness": {"status": "FRESH"},
    }
    n1 = append_intraday_from_snapshot(tmp_path, snap)
    n2 = append_intraday_from_snapshot(tmp_path, snap)
    assert n1 >= 2
    assert n2 == 0
    assert count_ledger_lines(tmp_path, "intraday_quotes.jsonl") >= 2


def test_eod_capture_mocked(tmp_path: Path):
    from market.learning_pipeline import ensure_today_eod_closes, learning_readiness_report

    idx = pd.date_range("2026-05-28", periods=3, freq="D")
    cols = pd.MultiIndex.from_tuples([("Close", "OXY"), ("Close", "WDC"), ("Close", "STX")])
    data = [[70.0, 80.0, 60.0], [71.0, 81.0, 61.0], [72.0, 82.0, 62.0]]
    df = pd.DataFrame(data, index=idx, columns=cols)

    with mock.patch("yfinance.download", return_value=df):
        result = ensure_today_eod_closes(tmp_path, force=True)
    assert result.get("captured", 0) >= 3
    report = learning_readiness_report(tmp_path)
    assert report["eod_close_observations"] >= 3


def test_learning_cycle_respects_disable_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AA_LEARNING_CAPTURE", "0")
    from market.learning_pipeline import run_learning_capture_cycle

    snap = {"executable_prices_eur": {"OXY": 71.0}, "generated_at_utc": "2026-01-01T12:00:00+00:00"}
    out = run_learning_capture_cycle(tmp_path, live_snapshot=snap, broker={"credentials_configured": True, "cash_eur": 100})
    assert out["intraday_appended"] == 0
    assert out["eod"].get("skipped") is True


def test_corrupt_manifest_recovers(tmp_path: Path):
    from market.learning_pipeline import _load_manifest, learning_root

    learning_root(tmp_path)
    (learning_root(tmp_path) / "learning_manifest.json").write_text("{not json", encoding="utf-8")
    manifest = _load_manifest(tmp_path)
    assert manifest["intraday_rows"] == 0
    assert manifest["schema_version"] == 1


def test_broker_snapshot_skips_without_credentials(tmp_path: Path):
    from market.learning_pipeline import append_broker_daily_snapshot

    out = append_broker_daily_snapshot(tmp_path, broker={"credentials_configured": False}, cash={})
    assert out.get("skipped") is True
    assert out.get("reason") == "broker_not_configured"


def test_broker_event_snapshot_liquidation(tmp_path: Path):
    from market.learning_pipeline import append_broker_event_snapshot, learning_readiness_report

    broker = {
        "credentials_configured": True,
        "positions_count": 0,
        "cash_eur": 674.66,
        "last_successful_sync_utc": "2026-06-08T10:00:00+00:00",
        "positions": [],
    }
    out = append_broker_event_snapshot(
        tmp_path,
        broker=broker,
        event="liquidation_complete",
        previous_positions_count=5,
    )
    assert out.get("ok") is True
    assert out.get("event") == "liquidation_complete"
    report = learning_readiness_report(tmp_path)
    assert report["broker_event_snapshots"] >= 1


def test_learning_cycle_offline_test(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AA_OFFLINE_COCKPIT_TEST", "1")
    from market.live_quote_engine import ensure_live_quotes_fresh
    from market.learning_pipeline import run_learning_capture_cycle

    snap = ensure_live_quotes_fresh(tmp_path, force=True)
    out = run_learning_capture_cycle(tmp_path, live_snapshot=snap, broker={"credentials_configured": False}, force_eod=False)
    assert out["intraday_appended"] >= 1
    assert out["readiness"]["learning_collection_active"] is True
