"""P5 realtime replay foundation gate tests (master prompt §14.6)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aa_intraday_data_quality import validate_bars, validate_replay_dataset
from aa_market_data import ReplayMarketDataProvider, ensure_sample_replay_data
from aa_realtime_replay import (
    QUALITY_FILE,
    STATUS_FILE,
    run_realtime_replay_sync,
)


def test_p5_replay_deterministic(tmp_path: Path) -> None:
    ensure_sample_replay_data(tmp_path)
    provider = ReplayMarketDataProvider(tmp_path / "market_data" / "replay")
    a = provider.get_historical_bars("SPY")
    b = provider.get_historical_bars("SPY")
    pd.testing.assert_frame_equal(a, b)


def test_p5_duplicate_bars_detected(tmp_path: Path) -> None:
    replay = ensure_sample_replay_data(tmp_path)
    bars_path = replay / "bars_5m" / "SPY.csv"
    df = pd.read_csv(bars_path)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    df.to_csv(bars_path, index=False)
    provider = ReplayMarketDataProvider(replay)
    res = validate_bars(provider.get_historical_bars("SPY"), ticker="SPY")
    assert res.status == "FAIL"
    assert res.duplicate_bars > 0


def test_p5_stale_quotes_warned(tmp_path: Path) -> None:
    replay = ensure_sample_replay_data(tmp_path)
    quotes_path = replay / "quotes" / "SPY.csv"
    pd.DataFrame([{"timestamp": "2019-01-01T14:30:00+00:00", "bid": 1.0, "ask": 1.1, "last": 1.05}]).to_csv(
        quotes_path, index=False
    )
    provider = ReplayMarketDataProvider(replay)
    res = validate_replay_dataset(
        provider,
        tickers=["SPY", "AAPL"],
        reference=pd.Timestamp("2020-06-01T12:00:00Z"),
    )
    assert res.stale_quote_rows >= 1 or any("stale" in w.lower() for w in res.warnings)


def test_p5_missing_spy_blocks_quality(tmp_path: Path) -> None:
    replay = ensure_sample_replay_data(tmp_path)
    (replay / "bars_5m" / "SPY.csv").unlink()
    provider = ReplayMarketDataProvider(replay)
    res = validate_replay_dataset(provider, tickers=["AAPL"], require_spy=True)
    assert res.status == "FAIL"
    assert res.missing_spy is True


def test_p5_quality_fail_does_not_change_champion(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    out.mkdir()
    (out / "latest_validated_run.json").write_text(
        json.dumps({"run_id": "good", "integrity_status": "PASS", "variant_id": "R3"}),
        encoding="utf-8",
    )
    replay = ensure_sample_replay_data(root)
    (replay / "bars_5m" / "SPY.csv").unlink()
    summary = run_realtime_replay_sync(root, out, tickers=["AAPL"])
    assert summary["data_quality_status"] == "FAIL"
    pointer = json.loads((out / "latest_validated_run.json").read_text(encoding="utf-8"))
    assert pointer["run_id"] == "good"


def test_p5_sync_writes_status(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    out.mkdir()
    (out / "latest_validated_run.json").write_text('{"integrity_status":"PASS"}', encoding="utf-8")
    summary = run_realtime_replay_sync(root, out)
    assert summary["status"] == "OK"
    assert (out / STATUS_FILE).is_file()
    assert (out / QUALITY_FILE).is_file()
    assert (root / "control" / STATUS_FILE).is_file()
