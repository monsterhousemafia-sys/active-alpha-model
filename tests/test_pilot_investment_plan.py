"""Investment plan scaled to broker cash."""
from __future__ import annotations

from analytics.pilot_investment_plan import build_investment_plan


def test_build_investment_plan_scales_to_cash(tmp_path):
    root = tmp_path
    (root / "paper/config").mkdir(parents=True)
    (root / "model_output_sp500_pit_t212").mkdir(parents=True)
    import pandas as pd

    pd.DataFrame(
        [
            {"ticker": "INTC", "target_weight": 0.08, "alpha_lcb": 0.5, "signal_date": "2026-06-01"},
            {"ticker": "WDC", "target_weight": 0.15, "alpha_lcb": 0.4, "signal_date": "2026-06-01"},
        ]
    ).to_csv(root / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False)

    plan = build_investment_plan(root, 400.0)
    assert plan["available_cash_eur"] == 400.0
    assert plan["investable_eur"] == 400.0
    assert plan["executable"]
    allocs = plan["allocations"]
    assert len(allocs) >= 2
    net_sum = sum(a["target_eur"] for a in allocs)
    gross_sum = sum(a.get("target_eur_gross", a["target_eur"]) for a in allocs)
    assert abs(gross_sum - 400.0) < 0.05
    assert net_sum < gross_sum
    assert all(a.get("estimated_one_way_cost_eur", 0) >= 0 for a in allocs)
    assert plan["primary_action"]["symbol"] == "INTC"


def test_build_investment_plan_fail_closed_no_cash(tmp_path):
    plan = build_investment_plan(tmp_path, 0.0)
    assert not plan["executable"]


def test_build_investment_plan_skips_below_min_position(tmp_path):
    import json

    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"min_position_eur": 25.0, "cash_buffer_pct": 5.0, "use_full_free_cash": False}}),
        encoding="utf-8",
    )
    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True)
    import pandas as pd

    pd.DataFrame(
        [
            {"ticker": "INTC", "target_weight": 0.95, "alpha_lcb": 0.5, "signal_date": "2026-06-01"},
            {"ticker": "CAT", "target_weight": 0.05, "alpha_lcb": 0.1, "signal_date": "2026-06-01"},
        ]
    ).to_csv(tmp_path / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False)

    plan = build_investment_plan(tmp_path, 400.0)
    syms = {a["symbol"] for a in plan["allocations"]}
    assert "INTC" in syms
    assert "CAT" not in syms
    assert all(float(a["target_eur"]) > 0 for a in plan["allocations"])
