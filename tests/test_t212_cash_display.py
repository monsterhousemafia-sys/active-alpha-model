from pathlib import Path

from integrations.trading212.t212_cash_display import (
    eur_amount_with_usd_suffix,
    eur_to_usd,
    format_cash_display_html,
    format_cash_display_plain,
    format_eur_line_html,
    usd_per_eur,
)
from integrations.trading212.t212_us_cost_model import (
    effective_cost_per_share,
    estimate_buy_cost_breakdown,
    format_cost_step_de,
    load_t212_cost_policy,
)


def test_eur_to_usd_conversion() -> None:
    assert eur_to_usd(100.0, 0.86) == 100.0 / 0.86
    assert usd_per_eur(0.86) == 1.0 / 0.86
    assert eur_to_usd(10.0, 0.0) is None


def test_format_eur_line_includes_usd_highlight() -> None:
    html = format_eur_line_html("Frei", 492.0, usd_to_eur_rate=0.92)
    assert "492.00 €" in html
    assert "USD" in html
    assert "font-weight:700" in html
    assert "534.78" in html


def test_format_cash_display_all_lines() -> None:
    html, footer = format_cash_display_html(
        cash_eur=100.0,
        cash_breakdown={
            "reserved_for_orders_eur": 5.0,
            "in_pies_eur": 10.0,
            "total_account_value_eur": 200.0,
        },
        fx={"ok": True, "usd_to_eur_rate": 0.9, "usd_per_eur": 1 / 0.9, "source": "T"},
    )
    assert html.count("USD") >= 4
    assert "Spot: 1 EUR" in footer


def test_cost_model_fx_fee_and_buffer() -> None:
    pol = load_t212_cost_policy(None)
    per_share = effective_cost_per_share(10.0, pol)
    assert per_share > 10.0
    assert per_share < 10.02
    est = estimate_buy_cost_breakdown(
        notional_eur=82.0,
        limit_price_eur=94.0,
        quantity=0.87,
        policy=pol,
    )
    assert est["estimated_fx_fee_eur"] > 0
    assert est["all_in_notional_eur"] >= 81.0
    assert est["estimated_reservation_uplift_eur"] == 0.0


def test_plain_cash_display_includes_usd() -> None:
    body, footer = format_cash_display_plain(
        cash_eur=100.0,
        cash_breakdown={},
        fx={"ok": True, "usd_to_eur_rate": 0.9, "usd_per_eur": 1 / 0.9},
    )
    assert "USD" in body
    assert "Spot:" in footer


def test_eur_amount_with_usd_suffix() -> None:
    s = eur_amount_with_usd_suffix(50.0, usd_to_eur_rate=0.9)
    assert "€" in s and "USD" in s


def test_format_cost_step_de(tmp_path: Path) -> None:
    line = format_cost_step_de(tmp_path, notional_eur=50.0, limit_price_eur=25.0, quantity=2.0)
    assert line is not None
    assert "T212-Kosten" in line
    assert "FX" in line
