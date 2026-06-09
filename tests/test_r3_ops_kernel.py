from pathlib import Path
from unittest.mock import patch

from analytics.pilot_portfolio_reevaluation import load_policy
from analytics.r3_live_capital import compute_worthwhile_positions
from analytics.r3_ops_kernel import resolve_phase_steps, run_ops_pipeline, run_ops_step


def test_resolve_phase_steps_from_policy(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_ops_kernel_policy.json").write_text("{}", encoding="utf-8")
    steps = resolve_phase_steps(tmp_path, "data_care")
    assert "quotes" in steps
    assert "cycle" in steps


def test_harmonized_reeval_policy_daily_alpha(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/pilot_day_trading.json").write_text(
        '{"reevaluation":{"min_drift_pct_to_flag":1.0,"min_trade_eur":5.0}}',
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_operations.json").write_text(
        '{"active_profile":"daily_alpha_h1","rebalance":{"min_weight_gap_pct":2.5},'
        '"budget":{"min_position_eur":25.0}}',
        encoding="utf-8",
    )
    pol = load_policy(tmp_path)
    assert pol.get("min_drift_pct_to_flag") == 2.5
    assert pol.get("min_trade_eur") == 25.0


def test_flat_depot_risk_off_no_plan_buys(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    capital = {
        "ok": True,
        "trusted": True,
        "planning_cash_eur": 675.0,
        "investable_eur": 675.0,
        "cash_eur": 675.0,
        "positions_count": 0,
        "broker": {"positions_count": 0, "positions": []},
    }
    plan = {
        "allocations": [{"symbol": "MU", "target_eur": 50.0, "alpha_lcb": 0.002, "model_weight_pct": 5.0}],
        "signal_date": "2026-06-09",
    }
    reeval = {
        "risk_on": False,
        "signals_ok": True,
        "champion_ok": True,
        "trade_required": False,
        "summary_de": "risk-off",
        "recommended_actions": [],
        "signal_date": "2026-06-09",
    }
    with patch("analytics.r3_live_capital.sync_live_capital_basis", return_value=capital), patch(
        "analytics.pilot_investment_plan.build_investment_plan",
        return_value=plan,
    ), patch(
        "analytics.pilot_portfolio_reevaluation.evaluate_live_portfolio_vs_champion",
        return_value=reeval,
    ), patch("analytics.r3_trading_functions.build_r3_trading_functions"):
        doc = compute_worthwhile_positions(tmp_path, force_sync=False, persist=True)
    assert doc.get("worthwhile_buy_count") == 0
    assert doc.get("risk_on") is False


def test_ops_pipeline_pre_us(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/AI_KERNEL.json").write_text('{"flags":{"auto_execute_real_money":false}}', encoding="utf-8")
    (tmp_path / "control/r3_ops_kernel_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/r3_worthwhile_positions_latest.json").write_text(
        '{"worthwhile_buys":[{"symbol":"NVDA","priority_score":30,"alpha_lcb":0.003}]}',
        encoding="utf-8",
    )

    def fake_step(root, step_id, **kwargs):
        ctx = kwargs.get("context") or {}
        if step_id == "capital":
            ctx["worthwhile"] = {"worthwhile_buys": [{"symbol": "NVDA", "priority_score": 30, "alpha_lcb": 0.003}]}
        return {
            "id": step_id,
            "ok": True,
            "detail_de": f"{step_id} OK",
            "top_picks": [{"symbol": "NVDA"}] if step_id == "top_picks" else None,
        }

    with patch("analytics.r3_ops_kernel.run_ops_step", side_effect=fake_step):
        doc = run_ops_pipeline(tmp_path, phase="pre_us", persist=True)
    assert doc.get("phase") == "pre_us"
    assert (tmp_path / "evidence/r3_ops_latest.json").is_file()
