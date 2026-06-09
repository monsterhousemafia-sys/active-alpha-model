"""Gewinn-Aktivierung — Orchestrator."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def test_activate_after_profit_minimal(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True, "top_picks": [{"ticker": "MU", "target_weight": 0.05}]}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 100.0, "allocations": [{"symbol": "MU", "model_weight_pct": 5.0}]}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_product_roles.json").write_text("{}", encoding="utf-8")

    with patch("analytics.t212_learning_sync.sync_t212_with_learning") as t212, patch(
        "analytics.king_plan_integration.rebuild_investment_plan_with_king",
        return_value={"ok": True, "investable_eur": 100.0},
    ), patch(
        "analytics.pilot_portfolio_reevaluation.run_periodic_reevaluation",
        return_value={"status": "OK", "exposure_check": {"under_invested": True}, "quote_fresh": True, "recommended_actions": []},
    ), patch(
        "analytics.r3_trading_functions.build_r3_trading_functions",
        return_value={
            "functions_active": 1,
            "primary_function_id": "initial_order",
            "stock_groups": {"new_buys": [{"symbol": "MU"}]},
            "initial_package": {"order_count": 1, "budget_eur": 100.0},
            "context": {"investable_eur": 100.0},
        },
    ), patch(
        "analytics.r3_t212_prognosis.build_r3_t212_daily_prognosis",
        return_value={"ok": True, "positions": 1},
    ), patch("analytics.gas_sell_steering.apply_gas_sell_steering"), patch(
        "analytics.gas_sell_steering.load_gas_sell_steering",
        return_value={"on_course": True, "gas_count": 1, "headline_de": "OK"},
    ), patch(
        "analytics.r3_freigabe.auto_prepare_freigabe_for_desktop",
        return_value={"package_ready": True},
    ), patch(
        "analytics.learning_cycle_audit.run_learning_cycle_audit",
        return_value={"ok": True, "live_metrics": {"n_mature": 0}},
    ), patch(
        "analytics.wallstreet_performance_audit.run_wallstreet_audit",
        return_value={"ok": True, "blockers": []},
    ):
        t212.return_value = {"ok": True, "cash_eur": 105.0, "positions_count": 0, "headline_de": "OK"}
        from analytics.r3_profit_activation import activate_after_profit

        doc = activate_after_profit(tmp_path, persist=True)
    assert doc.get("ok") is True
    assert doc.get("primary_function") == "initial_order"
    assert (tmp_path / "evidence/r3_profit_activation_latest.json").is_file()
