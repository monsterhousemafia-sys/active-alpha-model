"""P11 statistical research validation tests."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_p11_variant_sources_include_research_variants():
    from research.p11.variants import p11_variant_sources

    src = p11_variant_sources(ROOT)
    assert "MOM_63_TOP12_STRICT" in src
    assert "MOM_63_TOP15_RECONSTRUCTED" in src
    assert src["MOM_63_TOP12_STRICT"].get("turnover_verified") is True


def test_p11_cost_stress_matrix_rows():
    from research.p11.cost_stress import run_cost_stress_all

    out = run_cost_stress_all(ROOT)
    rows = out.get("rows") or []
    assert len(rows) >= 5
    statuses = {r.get("evaluation_status") for r in rows}
    assert statuses & {"EVALUABLE", "NOT_EVALUABLE", "BLOCKED"}


def test_p11_paper_practicality_500eur():
    from research.p11.paper_practicality import INITIAL_PAPER_CAPITAL_EUR, analyze_paper_practicality

    p = analyze_paper_practicality(top_k=12)
    assert p["initial_paper_capital_eur"] == INITIAL_PAPER_CAPITAL_EUR == 500.0
    assert p["real_money_capital_eur"] == 0.0
    assert p["simulation_only"] is True


def test_p11_dsr_conditional():
    from research.p11.dsr import RETURN_COST_LIMITATION, run_dsr_all

    out = run_dsr_all(ROOT)
    assert out.get("limitation") == RETURN_COST_LIMITATION
    assert out.get("overall_status") in {"CONDITIONAL", "NOT_AVAILABLE"}


def test_p11_pbo_matrix_partial():
    from research.p11.pbo_cscv import assess_pbo_matrix

    out = assess_pbo_matrix(ROOT)
    assert out.get("status") == "PARTIAL_WITH_REQUIRED_MATRIX_BUILD"


def test_p11_robustness_evaluable():
    from research.p11.robustness import run_robustness_all

    out = run_robustness_all(ROOT)
    assert out.get("overall_status") in {"PASS", "PARTIAL"}


def test_p11_ranking_not_promoted():
    from research.p11.cost_stress import run_cost_stress_all
    from research.p11.dsr import run_dsr_all
    from research.p11.paper_practicality import analyze_paper_practicality
    from research.p11.ranking import build_research_ranking
    from research.p11.robustness import run_robustness_all

    ranking = build_research_ranking(
        cost_stress=run_cost_stress_all(ROOT),
        dsr=run_dsr_all(ROOT),
        robustness=run_robustness_all(ROOT),
        paper=analyze_paper_practicality(),
        champion_id="R3_w075_q065_noexit",
    )
    assert ranking.get("champion_changed") is False
    for row in ranking.get("ranking") or []:
        assert row.get("promotion_status") == "NOT_PROMOTED"
        assert row.get("live_authorization") == "NOT_LIVE_AUTHORIZED"
