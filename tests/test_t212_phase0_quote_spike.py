"""Phase 0 quote spike analysis helpers."""
from __future__ import annotations

from integrations.trading212.t212_quote_spike_analysis import (
    analyze_position_price_units,
    discover_price_fields,
    filter_instruments_by_tickers,
    summarize_positions_for_pricing,
)


def test_discover_price_fields_on_position_shape() -> None:
    payload = [{"currentPrice": 107.5, "quantity": 0.57, "instrument": {"ticker": "INTC_US_EQ"}}]
    fields = discover_price_fields(payload)
    assert any("currentPrice" in f["path"] for f in fields)


def test_instruments_champion_filter() -> None:
    rows = [
        {"ticker": "STX_US_EQ", "isin": "X", "currencyCode": "USD"},
        {"ticker": "AAPL_US_EQ", "isin": "Y"},
    ]
    out = filter_instruments_by_tickers(rows, ["STX_US_EQ"])
    assert len(out) == 1
    assert out[0]["ticker"] == "STX_US_EQ"


def test_position_eur_implied_vs_raw_price_warning() -> None:
    summary = summarize_positions_for_pricing(
        [
            {
                "instrument": {"ticker": "STX_US_EQ"},
                "quantity": 0.34,
                "currentPrice": 928.16,
                "walletImpact": {"currency": "EUR", "currentValue": 50.0, "totalCost": 51.0},
            }
        ]
    )
    warnings = analyze_position_price_units(summary)
    assert warnings and "STX" in warnings[0]
