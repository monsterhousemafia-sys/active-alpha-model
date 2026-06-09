"""Quote plausibility sanitization."""
from __future__ import annotations

from paper.p16d.quote_plausibility import sanitize_executable_prices, sanitize_price_eur


def test_sanitize_rejects_absurd_mu_price_for_orders() -> None:
    adj, changed, reason = sanitize_price_eur("MU", 889.0, for_orders=True)
    assert changed
    assert reason == "ABOVE_CAP_BLOCKED"
    assert adj is None


def test_sanitize_legacy_cap_when_not_for_orders() -> None:
    adj, changed, reason = sanitize_price_eur("MU", 889.0, for_orders=False)
    assert changed
    assert reason == "ABOVE_CAP"
    assert adj is not None and adj < 300


def test_sanitize_t212_no_cap_shrink() -> None:
    adj, changed, reason = sanitize_price_eur("STX", 798.0, source="T212", for_orders=True)
    assert not changed
    assert reason == "OK"
    assert adj == 798.0


def test_sanitize_keeps_plausible_intc() -> None:
    adj, changed, _ = sanitize_price_eur("INTC", 94.0)
    assert not changed
    assert adj == 94.0


def test_sanitize_executable_prices_map() -> None:
    out = sanitize_executable_prices({"MU": 900.0, "INTC": 40.0, "OXY": 55.0})
    assert out["had_adjustments"]
    assert out["executable_prices_eur"]["MU"] < 300
    assert out["executable_prices_eur"]["INTC"] == 40.0
