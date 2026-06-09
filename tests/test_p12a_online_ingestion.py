"""P12A read-only online market data ingestion tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aa_market_data import ensure_sample_replay_data
from research.p12a.ingestion import run_ingestion_cycle
from research.p12a.observation_ledger import read_ledger
from research.p12a.providers.replay_fixture import ReadOnlyReplayFixtureProvider
from research.p12a.quality import assess_online_quotes
from research.p12a.replay import verify_replay_determinism


def test_p12a_readonly_provider_no_order_routing(tmp_path: Path) -> None:
    replay = ensure_sample_replay_data(tmp_path)
    provider = ReadOnlyReplayFixtureProvider(replay)
    assert provider.read_only is True
    assert provider.order_routing_enabled is False
    quotes = provider.fetch_quotes(["SPY", "AAPL"])
    assert not quotes.empty
    assert "received_at_utc" in quotes.columns


def test_p12a_quality_missing_symbol(tmp_path: Path) -> None:
    df = pd.DataFrame([{"ticker": "SPY", "last": 100.0, "timestamp": "2020-01-02T14:30:00+00:00"}])
    res = assess_online_quotes(df, expected_symbols=["SPY", "AAPL"])
    assert res.status == "FAIL"
    assert "AAPL" in res.missing_symbols


def test_p12a_ingestion_cycle(tmp_path: Path) -> None:
    out = run_ingestion_cycle(tmp_path)
    assert out["quality_passed"] is True
    assert out["replay_deterministic"] is True
    assert out["row_count"] >= 1
    ledger = read_ledger(tmp_path)
    assert len(ledger) >= 1
    assert ledger[0].get("broker_order_sent") is False


def test_p12a_replay_determinism(tmp_path: Path) -> None:
    out = run_ingestion_cycle(tmp_path)
    check = verify_replay_determinism(tmp_path, out["capture_id"])
    assert check["deterministic"] is True
