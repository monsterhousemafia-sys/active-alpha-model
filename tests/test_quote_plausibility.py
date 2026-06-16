"""Quote plausibility sanitization."""
from __future__ import annotations

from pathlib import Path

from paper.p16d.quote_plausibility import sanitize_executable_prices, sanitize_price_eur


def test_sanitize_accepts_mu_with_panel_anchor() -> None:
    anchor = {"MU": 785.0}
    adj, changed, reason = sanitize_price_eur(
        "MU", 809.0, for_orders=True, anchor_prices_eur=anchor
    )
    assert not changed
    assert reason == "OK"
    assert adj == 809.0


def test_sanitize_rejects_mu_far_from_anchor_for_orders() -> None:
    anchor = {"MU": 785.0}
    adj, changed, reason = sanitize_price_eur(
        "MU", 200.0, for_orders=True, anchor_prices_eur=anchor
    )
    assert changed
    assert reason == "BELOW_ANCHOR_BLOCKED"
    assert adj is None


def test_sanitize_legacy_cap_when_not_for_orders_without_anchor() -> None:
    adj, changed, reason = sanitize_price_eur("MU", 5000.0, for_orders=False)
    assert changed
    assert reason == "ABOVE_CAP"
    assert adj is not None and adj < 1100


def test_sanitize_t212_no_cap_shrink() -> None:
    adj, changed, reason = sanitize_price_eur("STX", 798.0, source="T212", for_orders=True)
    assert not changed
    assert reason == "OK"
    assert adj == 798.0


def test_sanitize_keeps_plausible_intc() -> None:
    adj, changed, _ = sanitize_price_eur("INTC", 94.0)
    assert not changed
    assert adj == 94.0


def test_sanitize_executable_prices_with_anchor() -> None:
    anchor = {"MU": 785.0, "INTC": 92.0, "OXY": 50.0}
    out = sanitize_executable_prices(
        {"MU": 810.0, "INTC": 94.0, "OXY": 55.0},
        anchor_prices_eur=anchor,
        for_orders=True,
    )
    assert not out["had_blocks"]
    assert out["executable_prices_eur"]["MU"] == 810.0
    assert out["executable_prices_eur"]["INTC"] == 94.0


def test_load_anchor_prices_for_sanitize_reads_panel(tmp_path: Path) -> None:
    pytest = __import__("pytest")
    try:
        import pandas as pd
    except ImportError:
        pytest.skip("pandas required")

    cache = tmp_path / "model_output_sp500_pit_t212" / "price_cache"
    cache.mkdir(parents=True)
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-08", "2026-06-09"]),
            "ticker": ["MU", "MU"],
            "Close": [800.0, 900.0],
        }
    )
    panel.to_parquet(cache / "ohlcv_panel.parquet", index=False)

    from paper.p16d.quote_plausibility import load_anchor_prices_for_sanitize

    anchors = load_anchor_prices_for_sanitize(tmp_path, ["MU"])
    assert "MU" in anchors
    assert anchors["MU"] > 700
