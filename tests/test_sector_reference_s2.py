"""Phase S2 — universe pipeline sector integration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_ops_refresh import refresh_universe_if_needed
from aa_sector_reference import clear_reference_cache, lookup_sector, resolve_reference_path
from aa_universe import _component_records_from_tables, load_tickers, save_universe_snapshot


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_reference_cache()
    yield
    clear_reference_cache()


def test_component_records_includes_sector_gics() -> None:
    df = pd.DataFrame(
        {
            "Symbol": ["AAPL", "XOM"],
            "Security": ["Apple Inc.", "Exxon"],
            "GICS Sector": ["Information Technology", "Energy"],
        }
    )
    records = _component_records_from_tables([df], source="wikipedia_sp500")
    by_tk = {r["ticker"]: r for r in records}
    assert by_tk["AAPL"]["sector_gics"] == "Information Technology"
    assert by_tk["AAPL"]["sector_coarse"] == "Technology"
    assert by_tk["XOM"]["sector_coarse"] == "Energy"


def test_save_universe_snapshot_persists_sector_columns(tmp_path: Path) -> None:
    records = [
        {
            "ticker": "MSFT",
            "source_symbol": "MSFT",
            "company": "Microsoft",
            "sector_gics": "Information Technology",
            "sector_coarse": "Technology",
            "source": "wikipedia_sp500",
        }
    ]
    cache = tmp_path / "universe_snapshots"
    path = save_universe_snapshot(records, cache, source_detail="test")
    df = pd.read_csv(path)
    assert "sector_gics" in df.columns
    assert "sector_coarse" in df.columns
    assert df.iloc[0]["sector_coarse"] == "Technology"
    latest = pd.read_csv(cache / "sp500_latest.csv")
    assert "sector_gics" in latest.columns


def test_refresh_universe_if_needed_updates_sector_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    records = [
        {
            "ticker": "NVDA",
            "source_symbol": "NVDA",
            "company": "NVIDIA",
            "sector_gics": "Information Technology",
            "sector_coarse": "Technology",
            "source": "wikipedia_sp500",
        }
    ]
    monkeypatch.setattr("aa_universe.fetch_wikipedia_sp500_components", lambda: records)
    logs: list[str] = []
    env = {
        "AA_PAPER_TICKER_SOURCE": "wikipedia_sp500",
        "AA_TICKER_CACHE_DIR": str(tmp_path / "universe_snapshots"),
        "AA_TICKER_CACHE_MAX_AGE_DAYS": "0",
        "AA_SECTOR_REFERENCE_FILE": "sector_reference.csv",
        "AA_PROJECT_ROOT": str(tmp_path),
    }
    ok = refresh_universe_if_needed(tmp_path, env, log=logs.append)
    assert ok is True
    ref = resolve_reference_path(tmp_path)
    assert ref.is_file()
    assert lookup_sector("NVDA", root=tmp_path) == "Technology"
    assert any("Sektor-Referenz" in line for line in logs)


def test_load_tickers_syncs_sector_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    records = [
        {
            "ticker": "AMD",
            "source_symbol": "AMD",
            "company": "AMD",
            "sector_gics": "Information Technology",
            "sector_coarse": "Technology",
            "source": "wikipedia_sp500",
        }
    ]
    monkeypatch.setattr(
        "aa_universe.fetch_wikipedia_sp500_components",
        lambda: records,
    )
    monkeypatch.setattr("aa_universe.update_membership_from_records", lambda *a, **k: (0, tmp_path / "ticker_membership.csv"))
    monkeypatch.setattr(
        "aa_universe.update_asset_master_from_records",
        lambda *a, **k: (0, 0, tmp_path / "asset_master.csv"),
    )

    args = MagicMock()
    args.ticker_source = "wikipedia_sp500"
    args.ticker_cache_dir = "universe_snapshots"
    args.ticker_cache_max_age_days = 0
    args.no_ticker_fallback = True
    args.no_save_universe_snapshot = False
    args.no_update_membership = False
    args.no_update_asset_master = False
    args.no_update_sector_reference = False
    args.membership_file = "ticker_membership.csv"
    args.asset_master_file = "asset_master.csv"
    args.benchmark = "SPY"
    args.extra_benchmarks = ""
    args.tickers = ""
    args.tickers_file = ""

    (tmp_path / "universe_snapshots").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"ticker": "AMD", "valid_from": "2012-01-01", "valid_to": "", "source": "t", "reason": "t"}]
    ).to_csv(tmp_path / "ticker_membership.csv", index=False)

    load_tickers(args)
    ref = tmp_path / "sector_reference.csv"
    assert ref.is_file()
    assert lookup_sector("AMD", root=tmp_path) == "Technology"
