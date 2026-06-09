"""Champion quote coverage gate."""
from __future__ import annotations

from market.champion_quote_gate import (
    coverage_label_de,
    require_champion_quote_coverage,
    symbols_from_orders,
)


def test_symbols_from_orders_buys_only() -> None:
    orders = [
        {"symbol": "STX", "side": "BUY"},
        {"symbol": "OXY", "side": "SELL"},
        {"symbol": "MU", "side": "BUY"},
    ]
    assert symbols_from_orders(orders) == ["MU", "STX"]


def test_require_coverage_ok() -> None:
    from pathlib import Path

    snap = {
        "generated_at_utc": "2026-06-02T12:00:00+00:00",
        "executable_prices_eur": {s: 50.0 for s in ("STX", "WDC", "MU")},
        "price_source_by_symbol": {"STX": "YAHOO_VALIDATED"},
    }
    gate = require_champion_quote_coverage(
        Path("."),
        symbols=["STX", "WDC", "MU"],
        quote_snapshot=snap,
        refresh_if_stale=False,
    )
    assert gate["ok"] is True
    assert gate["quote_coverage_label_de"] == "3/3 Kurse OK"


def test_require_coverage_blocks_missing() -> None:
    from pathlib import Path

    snap = {"executable_prices_eur": {"STX": 90.0}, "price_source_by_symbol": {}}
    gate = require_champion_quote_coverage(
        Path("."),
        symbols=["STX", "CAT", "AMD"],
        quote_snapshot=snap,
        refresh_if_stale=False,
    )
    assert gate["ok"] is False
    assert "CAT" in gate["coverage"]["missing_symbols"]
    assert coverage_label_de(gate["coverage"]) == "1/3 Kurse"
