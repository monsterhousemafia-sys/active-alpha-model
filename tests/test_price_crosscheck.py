from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analytics.price_crosscheck import (
    crosscheck_blocks_signal_refresh,
    evaluate_price_crosscheck,
    load_primary_closes,
    resolve_crosscheck_symbols,
    run_price_crosscheck,
)
from research.p12a.providers.stooq_readonly import ReadOnlyStooqProvider, stooq_us_symbol
from research.p12a.providers.yahoo_chart_readonly import ReadOnlyYahooChartProvider


def _write_panel(root: Path, rows: list[dict]) -> None:
    cache = root / "model_output_sp500_pit_t212" / "price_cache"
    cache.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(cache / "ohlcv_panel.parquet", index=False)


def test_stooq_us_symbol_mapping():
    assert stooq_us_symbol("SPY") == "spy.us"
    assert stooq_us_symbol("aapl") == "aapl.us"


def test_load_primary_closes_latest_per_symbol(tmp_path: Path):
    _write_panel(
        tmp_path,
        [
            {"date": "2026-06-10", "ticker": "SPY", "Close": 100.0},
            {"date": "2026-06-11", "ticker": "SPY", "Close": 101.0},
            {"date": "2026-06-11", "ticker": "AMD", "Close": 50.0},
        ],
    )
    closes = load_primary_closes(tmp_path, ["SPY", "AMD"])
    assert closes["SPY"]["close"] == 101.0
    assert closes["SPY"]["as_of"] == "2026-06-11"
    assert closes["AMD"]["close"] == 50.0


def test_evaluate_price_crosscheck_pass_when_aligned(tmp_path: Path, monkeypatch):
    _write_panel(
        tmp_path,
        [
            {"date": "2026-06-11", "ticker": "SPY", "Close": 500.0},
            {"date": "2026-06-11", "ticker": "AMD", "Close": 120.0},
        ],
    )
    policy = {
        "enabled": True,
        "symbols_mode": "spy_plus_champion",
        "extra_symbols": ["SPY", "AMD"],
        "thresholds": {
            "warn_divergence_pct": 1.0,
            "fail_divergence_pct": 3.0,
            "min_reference_coverage_ratio": 0.5,
            "require_spy_match": True,
        },
        "fail_closed": {
            "block_signal_refresh_on_fail": True,
            "block_signal_refresh_on_warn": False,
            "block_signal_refresh_on_missing_spy": True,
        },
        "network": {"max_reference_symbols_per_run": 2},
    }

    def fake_fetch(self, symbol: str, *, timeout_s: float = 12.0):
        prices = {"SPY": 500.5, "AMD": 120.2}
        sym = symbol.upper()
        if sym not in prices:
            return None
        return {
            "symbol": sym,
            "close": prices[sym],
            "as_of": "2026-06-11",
            "source": "READONLY_STOOQ",
        }

    monkeypatch.setattr(ReadOnlyStooqProvider, "fetch_last_close", fake_fetch)
    doc = evaluate_price_crosscheck(tmp_path, policy=policy, fetch_reference=True)
    assert doc["verdict"] == "pass"
    assert doc["ok"] is True
    assert doc["block_signal_refresh"] is False
    assert doc["spy_status"] == "pass"


def test_evaluate_price_crosscheck_fail_blocks_refresh(tmp_path: Path, monkeypatch):
    _write_panel(tmp_path, [{"date": "2026-06-11", "ticker": "SPY", "Close": 500.0}])
    policy = {
        "enabled": True,
        "symbols_mode": "spy_plus_champion",
        "extra_symbols": ["SPY"],
        "thresholds": {
            "warn_divergence_pct": 1.0,
            "fail_divergence_pct": 3.0,
            "min_reference_coverage_ratio": 0.5,
            "require_spy_match": True,
        },
        "fail_closed": {"block_signal_refresh_on_fail": True},
        "network": {"max_reference_symbols_per_run": 5},
    }

    monkeypatch.setattr(
        ReadOnlyStooqProvider,
        "fetch_last_close",
        lambda self, symbol, *, timeout_s=12.0: {
            "symbol": "SPY",
            "close": 520.0,
            "as_of": "2026-06-11",
            "source": "READONLY_STOOQ",
        },
    )
    doc = evaluate_price_crosscheck(tmp_path, policy=policy, fetch_reference=True)
    assert doc["verdict"] == "fail"
    assert crosscheck_blocks_signal_refresh(doc) is True


def test_run_price_crosscheck_persists_evidence(tmp_path: Path, monkeypatch):
    _write_panel(tmp_path, [{"date": "2026-06-11", "ticker": "SPY", "Close": 100.0}])
    monkeypatch.setattr(
        ReadOnlyStooqProvider,
        "fetch_last_close",
        lambda self, symbol, *, timeout_s=12.0: {
            "symbol": "SPY",
            "close": 100.1,
            "as_of": "2026-06-11",
            "source": "READONLY_STOOQ",
        },
    )
    doc = run_price_crosscheck(tmp_path, persist=True, fetch_reference=True)
    assert (tmp_path / "evidence/price_crosscheck_latest.json").is_file()
    assert doc["verdict"] == "pass"


def test_evaluate_price_crosscheck_stale_primary_is_warn_not_fail(tmp_path: Path, monkeypatch):
    _write_panel(tmp_path, [{"date": "2026-06-09", "ticker": "SPY", "Close": 500.0}])
    policy = {
        "enabled": True,
        "symbols_mode": "spy_plus_champion",
        "extra_symbols": ["SPY"],
        "thresholds": {
            "warn_divergence_pct": 1.0,
            "fail_divergence_pct": 3.0,
            "min_reference_coverage_ratio": 0.5,
            "require_spy_match": True,
        },
        "fail_closed": {"block_signal_refresh_on_fail": True, "block_signal_refresh_on_warn": False},
        "network": {"max_reference_symbols_per_run": 2},
    }

    monkeypatch.setattr(
        ReadOnlyStooqProvider,
        "fetch_last_close",
        lambda self, symbol, *, timeout_s=12.0: None,
    )
    monkeypatch.setattr(
        ReadOnlyYahooChartProvider,
        "fetch_last_close",
        lambda self, symbol, *, timeout_s=12.0: {
            "symbol": "SPY",
            "close": 520.0,
            "as_of": "2026-06-12",
            "source": "READONLY_YAHOO_CHART",
        },
    )
    doc = evaluate_price_crosscheck(tmp_path, policy=policy, fetch_reference=True)
    assert doc["verdict"] == "warn"
    assert doc["block_signal_refresh"] is False
    assert doc["spy_status"] == "stale_primary"


def test_resolve_crosscheck_symbols_includes_spy_and_champion():
    syms = resolve_crosscheck_symbols(Path("."), {"symbols_mode": "spy_plus_champion", "extra_symbols": ["SPY"]})
    assert "SPY" in syms
    assert "AMD" in syms
