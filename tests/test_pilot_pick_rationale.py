from analytics.pilot_pick_rationale import (
    METHODOLOGY_DE,
    explain_primary_pick,
    explain_symbol_from_model_row,
    rationale_one_liner,
)


def test_missing_row_fail_closed() -> None:
    doc = explain_symbol_from_model_row(None, {"signal_date": "2026-06-01"}, symbol="INTC")
    assert doc["status"] == "MISSING"
    assert "fehlt" in doc["summary_de"].lower() or "Keine" in doc["summary_de"]


def test_ok_lists_csv_fields_only() -> None:
    row = {
        "symbol": "INTC",
        "target_weight": 0.08,
        "alpha_lcb": 0.012,
        "rank_score": 0.91,
        "eligible": True,
        "sector": "Technology",
    }
    meta = {"signal_date": "2026-06-01", "risk_on": True, "target_exposure": 0.95}
    doc = explain_symbol_from_model_row(row, meta, symbol="INTC")
    assert doc["status"] == "OK"
    text = " ".join(doc["factors_de"])
    assert "alpha_lcb" in text
    assert "rank_score" in text
    assert "Semiconductor" not in text  # no invented sector stories


def test_not_eligible_mentioned() -> None:
    doc = explain_symbol_from_model_row(
        {"eligible": False, "alpha_lcb": 0.01, "target_weight": 0.05},
        {"signal_date": "2026-06-01"},
        symbol="X",
    )
    assert any("eligible=false" in f for f in doc["factors_de"])


def test_methodology_names_champion() -> None:
    assert "R3_w075" in METHODOLOGY_DE
    assert "alpha_lcb" in METHODOLOGY_DE


def test_rationale_one_liner_truncates() -> None:
    doc = {"status": "OK", "summary_de": "A" * 200, "factors_de": []}
    assert len(rationale_one_liner(doc, max_len=50)) <= 51
