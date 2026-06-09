"""T212-first instrument quote helpers."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

from integrations.trading212.t212_instrument_quotes import (
    PRICE_SOURCE_T212_HELD,
    champion_quote_coverage,
    merge_t212_yahoo_prices,
    symbol_to_t212_ticker,
    t212_ticker_to_symbol,
    verify_champion_instruments,
)


def test_symbol_ticker_roundtrip() -> None:
    assert symbol_to_t212_ticker("STX") == "STX_US_EQ"
    assert t212_ticker_to_symbol("GOOGL_US_EQ") == "GOOGL"


def test_merge_t212_overrides_yahoo() -> None:
    prices, sources, audit = merge_t212_yahoo_prices(
        champion_symbols=["STX", "MU"],
        t212_prices={"STX": 95.0},
        t212_sources={"STX": PRICE_SOURCE_T212_HELD},
        yahoo_prices={"STX": 900.0, "MU": 889.0},
        yahoo_valid={"STX": True, "MU": True},
    )
    assert prices["STX"] == 95.0
    assert sources["STX"] == PRICE_SOURCE_T212_HELD
    assert "MU" in audit["blocked"]


def test_champion_coverage_all_present() -> None:
    cov = champion_quote_coverage({"STX": 1.0, "WDC": 2.0}, required_symbols=["STX", "WDC"])
    assert cov["coverage_ok"]


def test_verify_champion_from_sample(tmp_path: Path) -> None:
    sample = tmp_path / "evidence" / "t212_champion_instruments_verified.json"
    sample.parent.mkdir(parents=True)
    rows = [{"ticker": f"{s}_US_EQ"} for s in ("STX", "WDC", "INTC")]
    sample.write_text(
        __import__("json").dumps({"champion_instruments": rows}),
        encoding="utf-8",
    )
    from integrations.trading212.t212_instrument_quotes import load_champion_instrument_rows

    loaded = load_champion_instrument_rows(tmp_path)
    ver = verify_champion_instruments(tmp_path, loaded)
    assert ver["matched"] == 3
    assert "GOOGL" in ver["missing_symbols"]


def test_fetch_held_positions_parses_wallet_impact(tmp_path: Path) -> None:
    from integrations.trading212.t212_instrument_quotes import fetch_held_position_prices_eur

    payload = [
        {
            "instrument": {"ticker": "INTC_US_EQ"},
            "quantity": 0.5,
            "walletImpact": {"currency": "EUR", "currentValue": 45.0},
        }
    ]
    with mock.patch(
        "integrations.trading212.t212_instrument_quotes._load_credentials",
        return_value=(mock.Mock(configured=True), "TEST"),
    ):
        with mock.patch(
            "integrations.trading212.t212_live_readonly_client.T212LiveReadOnlyClient"
        ) as cls:
            cls.return_value.get.return_value = payload
            prices = fetch_held_position_prices_eur(tmp_path, symbols={"INTC"}, force=True)
    assert prices["INTC"] == 90.0
