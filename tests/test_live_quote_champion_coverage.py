"""Champion 13/13 quote coverage in live snapshot."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS
from paper.p16d.instrument_identity import CHAMPION_EXECUTABLE_FILL, INSTRUMENT_DEFS


def test_instrument_defs_cover_all_champion_symbols() -> None:
    assert CHAMPION_EXECUTABLE_FILL == frozenset(CHAMPION_SYMBOLS)
    for sym in CHAMPION_SYMBOLS:
        assert sym in INSTRUMENT_DEFS
        assert INSTRUMENT_DEFS[sym]["provider_symbol"] == sym


def test_refresh_snapshot_has_champion_sources_and_coverage(tmp_path: Path) -> None:
    from market.live_quote_engine import refresh_live_quotes, snapshot_path

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    yahoo_prices = {sym: 50.0 + i for i, sym in enumerate(sorted(CHAMPION_SYMBOLS))}
    conversions = [
        {
            "user_reference_symbol": sym,
            "converted_price_eur": yahoo_prices[sym],
            "conversion_valid": True,
            "quote_currency": "USD",
            "market_event_time_utc": now,
            "data_quality_gate": "PASS",
        }
        for sym in CHAMPION_SYMBOLS
    ]
    batch = {
        "provider": "READONLY_YFINANCE",
        "executable_prices_eur": yahoo_prices,
        "prices_eur": yahoo_prices,
        "data_quality_gate": "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE",
        "fx_runtime_gate": "FX_PASS",
        "incident_count": 0,
        "valid_instrument_observations": len(CHAMPION_SYMBOLS),
        "generated_at_utc": now,
        "instrument_conversions": conversions,
    }
    with mock.patch("paper.p16d.forward_collect.collect_post_baseline_batch", return_value=batch):
        with mock.patch("market.live_quote_engine.build_identity_bindings", return_value={"primary": {"entries": []}}):
            with mock.patch(
                "integrations.trading212.t212_instrument_quotes.fetch_held_position_prices_eur",
                return_value={"STX": 120.0},
            ):
                snap = refresh_live_quotes(tmp_path, force=True)

    assert snapshot_path(tmp_path).is_file()
    assert len(snap["executable_prices_eur"]) == len(CHAMPION_SYMBOLS)
    cov = snap.get("champion_quote_coverage") or {}
    assert cov.get("coverage_ok") is True
    assert cov.get("covered_count") == len(CHAMPION_SYMBOLS)
    assert snap["price_source_by_symbol"]["STX"] == "T212"
    assert snap["price_source_by_symbol"]["MU"] == "YAHOO_VALIDATED"
