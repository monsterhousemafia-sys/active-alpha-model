"""Phase S3 — yfinance fallback and ensure_sector_reference_fresh."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from aa_sector_reference import (
    clear_reference_cache,
    collect_run_tickers,
    ensure_sector_reference_fresh,
    lookup_sector,
    resolve_missing_sectors_yfinance,
    resolve_reference_path,
    resolve_yfinance_cache_path,
)
from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_reference_cache()
    yield
    clear_reference_cache()


def test_resolve_missing_sectors_yfinance_uses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = resolve_yfinance_cache_path(tmp_path)
    monkeypatch.setattr(
        "aa_sector_reference._fetch_yfinance_sector_raw",
        lambda t: ("Communication Services", "Telecom") if t == "CIEN" else ("", ""),
    )
    records1, meta1 = resolve_missing_sectors_yfinance(["CIEN"], cache, ttl_days=7, root=tmp_path)
    assert len(records1) == 1
    assert records1[0]["ticker"] == "CIEN"
    assert records1[0]["sector_coarse"] == "Communication"
    assert meta1["network_fetches"] == 1

    monkeypatch.setattr(
        "aa_sector_reference._fetch_yfinance_sector_raw",
        lambda t: (_ for _ in ()).throw(AssertionError("should use cache")),
    )
    records2, meta2 = resolve_missing_sectors_yfinance(["CIEN"], cache, ttl_days=7, root=tmp_path)
    assert len(records2) == 1
    assert meta2["cache_hits"] == 1
    assert meta2["network_fetches"] == 0


def test_ensure_sector_reference_fresh_yfinance_cien(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aa_sector_reference._universe_refresh_needed", lambda *a, **k: False)
    monkeypatch.setattr(
        "aa_sector_reference._fetch_yfinance_sector_raw",
        lambda t: ("Communication Services", "Networking") if t == "CIEN" else ("", ""),
    )
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    env = {
        "AA_SECTOR_REFERENCE_MODE": "auto",
        "AA_SECTOR_YFINANCE_FALLBACK": "1",
        "AA_SECTOR_REFERENCE_FILE": "sector_reference.csv",
        "AA_SECTOR_YFINANCE_CACHE_FILE": "sector_yfinance_cache.json",
        "AA_PROJECT_ROOT": str(tmp_path),
    }
    out = ensure_sector_reference_fresh(tmp_path, env)
    assert out["refreshed"] is True
    assert lookup_sector("CIEN", root=tmp_path) == "Communication"
    cov = out["champion_coverage"]
    assert "CIEN" not in (cov.get("unknown_tickers") or [])


def test_collect_run_tickers_includes_champion_and_portfolio(tmp_path: Path) -> None:
    out_dir = tmp_path / "model_output_sp500_pit_t212"
    out_dir.mkdir(parents=True)
    import pandas as pd

    pd.DataFrame({"ticker": ["INTC"], "target_weight": [0.1]}).to_csv(
        out_dir / "latest_target_portfolio.csv", index=False
    )
    tickers = collect_run_tickers(tmp_path, {})
    for sym in CHAMPION_SYMBOLS:
        assert sym in tickers
    assert "INTC" in tickers


def test_ensure_disabled_skips_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "aa_sector_reference._fetch_yfinance_sector_raw",
        lambda t: (_ for _ in ()).throw(AssertionError("no network")),
    )
    out = ensure_sector_reference_fresh(tmp_path, {"AA_SECTOR_REFERENCE_MODE": "off"})
    assert out["refreshed"] is False
    assert out["reason"] == "DISABLED"


def test_yfinance_records_merge_into_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "aa_sector_reference._fetch_yfinance_sector_raw",
        lambda t: ("Technology", "Electronic Components") if t == "CIEN" else ("", ""),
    )
    ref = resolve_reference_path(tmp_path)
    records, _ = resolve_missing_sectors_yfinance(["CIEN"], resolve_yfinance_cache_path(tmp_path), root=tmp_path)
    from aa_sector_reference import update_sector_reference_from_records

    update_sector_reference_from_records(
        records, ref, valid_from="2026-06-04", source_detail="yfinance_fallback", root=tmp_path
    )
    assert lookup_sector("CIEN", root=tmp_path) != "Unknown"
    cache_doc = json.loads(resolve_yfinance_cache_path(tmp_path).read_text(encoding="utf-8"))
    assert "CIEN" in cache_doc.get("entries", {})
