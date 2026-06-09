"""R3 Evidence-Metriken — keine erfundenen Anzeigewerte."""
from __future__ import annotations

from analytics.r3_evidence_metrics import (
    MISSING,
    pipeline_broker_metric,
    pipeline_kreis_metric,
    system_quotes_metric,
    trading_cycle_stage_metric,
)


def test_missing_evidence_returns_dash() -> None:
    m = trading_cycle_stage_metric("account", {}, evidence_ref="evidence/x.json")
    assert m["display_de"] == MISSING
    assert m["fields_de"] == []


def test_account_from_cash_fields_only() -> None:
    m = trading_cycle_stage_metric(
        "account",
        {"cash_eur": 674.66, "investable_eur": 640.93},
        evidence_ref="evidence/r3_t212_api_bond_latest.json",
    )
    assert "€" in m["display_de"]
    assert "674" in m["display_de"] or "675" in m["display_de"]
    assert "cash_eur" in m["fields_de"]


def test_ingest_uses_price_latest_not_invented_count() -> None:
    m = trading_cycle_stage_metric(
        "ingest",
        {"ok": True, "price_latest": "2026-06-05"},
        evidence_ref="evidence/r3_browser_ingest_latest.json",
    )
    assert m["display_de"] == "2026-06-05"
    assert m["fields_de"] == ["price_latest"]


def test_broker_metric_skips_missing_fields() -> None:
    m = pipeline_broker_metric({"cash_eur": 500.0}, {}, evidence_ref="evidence/bond.json")
    assert m["display_de"] != MISSING
    assert "500" in m["display_de"]
    assert "investable_eur" not in m["fields_de"] or m["display_de"].count("·") == 0


def test_kreis_requires_green_and_total() -> None:
    assert pipeline_kreis_metric({}, evidence_ref="x")["display_de"] == MISSING
    assert pipeline_kreis_metric({"green": 2, "total": 6}, evidence_ref="x")["display_de"] == "2/6"


def test_quotes_missing_when_zero() -> None:
    m = system_quotes_metric(None, evidence_ref="snap", field="executable_prices_eur")
    assert m["display_de"] == MISSING
