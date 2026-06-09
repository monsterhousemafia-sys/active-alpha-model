"""P6 behavioral feature research gate tests (master prompt §15.6)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aa_behavioral_features import (
    compute_point_features,
    finalize_session_features,
    is_session_complete,
)
from aa_behavioral_research import STATUS_FILE, run_behavioral_research_sync
from aa_market_data import ReplayMarketDataProvider, ensure_sample_replay_data
from aa_realtime_replay import run_realtime_replay_sync


def test_p6_no_finalize_before_session_close(tmp_path: Path) -> None:
    replay = ensure_sample_replay_data(tmp_path)
    provider = ReplayMarketDataProvider(replay)
    bars = provider.get_historical_bars("SPY").iloc[:3]
    spy = bars
    session_date = pd.Timestamp(bars.index.max()).strftime("%Y-%m-%d")
    assert is_session_complete(bars, session_date) is False
    result = finalize_session_features(bars, spy, session_date=session_date)
    assert result.status == "SESSION_INCOMPLETE"


def test_p6_no_lookahead(tmp_path: Path) -> None:
    replay = ensure_sample_replay_data(tmp_path)
    provider = ReplayMarketDataProvider(replay)
    bars = provider.get_historical_bars("AAPL")
    spy = provider.get_historical_bars("SPY")
    as_of = pd.Timestamp(bars.index[2]).tz_convert("UTC")
    before = compute_point_features(bars, spy, as_of=as_of)
    mutated = bars.copy()
    mutated.loc[mutated.index[3:], "close"] = 999.0
    mutated.loc[mutated.index[3:], "volume"] = 999999.0
    after = compute_point_features(mutated, spy, as_of=as_of)
    for key in (
        "relative_volume",
        "volume_shock",
        "close_vs_vwap",
        "relative_intraday_return_vs_spy",
        "intraday_realized_volatility",
        "high_to_close_reversal",
    ):
        assert before[key] == after[key]


def test_p6_deterministic_from_replay(tmp_path: Path) -> None:
    from aa_behavioral_features import build_feature_table

    replay = ensure_sample_replay_data(tmp_path)
    provider = ReplayMarketDataProvider(replay)
    a, _ = build_feature_table(provider, ["SPY", "AAPL"])
    b, _ = build_feature_table(provider, ["SPY", "AAPL"])
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_p6_champion_unchanged(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    out.mkdir()
    champion = {"run_id": "good", "integrity_status": "PASS", "variant_id": "R3_w075_q065_noexit"}
    (out / "latest_validated_run.json").write_text(json.dumps(champion), encoding="utf-8")
    run_realtime_replay_sync(root, out)
    summary = run_behavioral_research_sync(root, out)
    assert summary["status"] == "OK"
    assert summary["champion_unchanged"] is True
    pointer = json.loads((out / "latest_validated_run.json").read_text(encoding="utf-8"))
    assert pointer["run_id"] == "good"


def test_p6_missing_data_blocks_via_quality(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    out.mkdir()
    (out / "latest_validated_run.json").write_text('{"integrity_status":"PASS"}', encoding="utf-8")
    ensure_sample_replay_data(root)
    (root / "market_data" / "replay" / "bars_5m" / "SPY.csv").unlink()
    run_realtime_replay_sync(root, out, tickers=["AAPL"])
    summary = run_behavioral_research_sync(root, out)
    assert summary["behavioral_research_status"] == "BLOCKED"
    assert summary["data_quality_status"] == "FAIL"


def test_p6_sync_writes_status(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    out.mkdir()
    (out / "latest_validated_run.json").write_text('{"integrity_status":"PASS","variant_id":"R3"}', encoding="utf-8")
    run_realtime_replay_sync(root, out)
    summary = run_behavioral_research_sync(root, out)
    assert summary["status"] == "OK"
    assert (out / STATUS_FILE).is_file()
    assert (root / "control" / STATUS_FILE).is_file()
    status = json.loads((out / STATUS_FILE).read_text(encoding="utf-8"))
    assert status["production_active"] is False
    assert "B2_ATTENTION_CONTINUATION" in [c["variant_id"] for c in status["challenger_results"]]
