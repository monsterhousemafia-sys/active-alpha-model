"""Tests for live quote freshness engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


def test_classify_freshness_stale_when_old():
    from market.live_quote_engine import classify_freshness

    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat()
    snap = {"generated_at_utc": old, "executable_prices_eur": {"OXY": 71.0}, "data_quality_gate": "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE"}
    fresh = classify_freshness(snap, max_age_s=120)
    assert fresh["status"] == "STALE"
    assert fresh["calculation_allowed"] is False


def test_classify_freshness_pass_when_recent():
    from market.live_quote_engine import classify_freshness

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snap = {"generated_at_utc": now, "executable_prices_eur": {"OXY": 71.0, "WDC": 80.0}, "data_quality_gate": "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE"}
    fresh = classify_freshness(snap, max_age_s=120)
    assert fresh["status"] == "FRESH"
    assert fresh["calculation_allowed"] is True


def test_refresh_live_quotes_writes_snapshot(tmp_path: Path):
    from market.live_quote_engine import load_live_quote_snapshot, refresh_live_quotes, snapshot_path

    batch = {
        "provider": "READONLY_YFINANCE",
        "executable_prices_eur": {"OXY": 71.0, "WDC": 80.0},
        "data_quality_gate": "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE",
        "fx_runtime_gate": "FX_PASS",
        "incident_count": 0,
        "valid_instrument_observations": 6,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "instrument_conversions": [
            {
                "user_reference_symbol": "OXY",
                "converted_price_eur": 71.0,
                "raw_price": 78.0,
                "quote_currency": "USD",
                "market_event_time_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "data_quality_gate": "PASS",
                "conversion_valid": True,
            }
        ],
    }
    with mock.patch("paper.p16d.forward_collect.collect_post_baseline_batch", return_value=batch):
        with mock.patch("market.live_quote_engine.build_identity_bindings", return_value={"primary": {"entries": []}}):
            with mock.patch(
                "integrations.trading212.t212_instrument_quotes.fetch_held_position_prices_eur",
                return_value={},
            ):
                snap = refresh_live_quotes(tmp_path, force=True)
    assert snap["executable_prices_eur"]["OXY"] == 71.0
    assert snapshot_path(tmp_path).is_file()
    loaded = load_live_quote_snapshot(tmp_path)
    assert loaded is not None
    assert loaded["freshness"]["status"] in ("FRESH", "STALE", "MISSING")
    assert loaded.get("executable_prices_eur")


def test_calculate_scenario_blocks_stale_prices():
    from ui.interactive_cockpit.services.scenario_planning_service import calculate_scenario

    out = calculate_scenario(
        {"capital_eur": 500, "reserve_eur": 50, "items": [{"symbol": "OXY", "amount_eur": 50}]},
        live_prices={"OXY": 71.0},
        price_freshness={"calculation_allowed": False, "reason": "stale"},
    )
    assert out["budget_gate"] == "FAIL"
    assert "BLOCKIERT" in out["planning_status"]


def test_build_pilot_gap_plan():
    from market.live_quote_engine import build_pilot_gap_plan

    rows = build_pilot_gap_plan(
        prices_eur={"WDC": 80.0},
        broker_positions=[{"ticker": "WDC_US_EQ", "currentValue": 50.0}],
    )
    wdc = next(r for r in rows if r["symbol"] == "WDC")
    assert wdc["gap_eur"] > 0
    assert wdc["estimated_shares_if_buy_gap"] > 0
