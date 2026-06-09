"""Quote session gate — freshness and champion coverage must align."""
from __future__ import annotations

from unittest import mock

from analytics.pilot_portfolio_reevaluation import _check_quotes_for_session, default_policy


def test_us_open_requires_coverage_for_required_symbols() -> None:
    snap = {
        "generated_at_utc": "2026-06-08T14:00:00+00:00",
        "executable_prices_eur": {"INTC": 40.0},
        "freshness": {"status": "FRESH", "calculation_allowed": True},
        "data_quality_gate": "PASS",
    }
    pol = default_policy()

    with mock.patch(
        "analytics.pilot_portfolio_reevaluation._us_session_open",
        return_value=True,
    ):
        ok, reason, us_open = _check_quotes_for_session(snap, pol, required_symbols=["INTC"])
        assert us_open is True
        assert ok is True
        assert reason == ""

        ok, reason, _ = _check_quotes_for_session(snap, pol, required_symbols=["INTC", "MU"])
        assert ok is False
        assert "unvollständig" in reason.lower() or "fehlend" in reason.lower()


def test_classify_freshness_fails_on_incomplete_champion_coverage() -> None:
    from market.live_quote_engine import classify_freshness

    snap = {
        "generated_at_utc": "2026-06-08T14:00:00+00:00",
        "executable_prices_eur": {"INTC": 40.0, "MU": 50.0},
        "data_quality_gate": "PARTIAL_PRICE_SANITIZED",
        "champion_quote_coverage": {
            "required_count": 13,
            "covered_count": 2,
            "missing_symbols": ["STX", "WDC"],
            "coverage_ok": False,
        },
    }
    fresh = classify_freshness(snap)
    assert fresh["status"] == "STALE"
    assert fresh["calculation_allowed"] is False


if __name__ == "__main__":
    test_us_open_requires_coverage_for_required_symbols()
    test_classify_freshness_fails_on_incomplete_champion_coverage()
    print("OK")
