"""Zuverlässigkeit — König→Plan→T212 geschlossener Kreis."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.alpha_model_background_engine import tick_alpha_model_background
from analytics.king_plan_integration import rebuild_investment_plan_with_king
from analytics.r3_closed_loop import rebalance_plan_inputs_stale, record_closed_loop_tick


def _seed_rebuild(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 5.0}, "active_profile": "daily_alpha_h1"}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_trading_functions_policy.json").write_text(
        json.dumps({"min_trade_eur": 5.0}),
        encoding="utf-8",
    )
    (tmp_path / "control/king_trading_assist_policy.json").write_text(
        json.dumps({"plan_integration": {"enabled": True}}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps({"follow_on_suggestions": [], "updated_at_utc": "2026-06-08T10:00:00+00:00"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "connected": True,
                "bonded": True,
                "cash_eur": 500.0,
                "cash_breakdown": {"planning_cash_eur": 500.0, "total_account_value_eur": 500.0},
                "positions": [],
                "positions_count": 0,
                "last_sync_utc": "2026-06-08T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "paper/config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "paper/config/p16c_cost_adjusted_initial_allocation_500eur.json").write_text(
        json.dumps(
            {
                "initial_capital_eur": 500,
                "positions": [
                    {"symbol_reference": "STX", "normalized_weight_pct": 50.0, "cost_adjusted_target_eur": 250},
                    {"symbol_reference": "AMD", "normalized_weight_pct": 50.0, "cost_adjusted_target_eur": 250},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_rebalance_inputs_stale_when_bond_newer(tmp_path: Path) -> None:
    _seed_rebuild(tmp_path)
    (tmp_path / "control/alpha_model_background_engine_state.json").write_text(
        json.dumps({"last_step_utc": {"rebalance_plan": "2026-06-08T08:00:00+00:00"}}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 400, "updated_at_utc": "2026-06-08T08:00:00+00:00"}),
        encoding="utf-8",
    )
    stale, reasons = rebalance_plan_inputs_stale(tmp_path)
    assert stale is True
    assert "bond_sync_newer" in reasons


def test_engine_bypasses_cooldown_when_inputs_stale(tmp_path: Path) -> None:
    _seed_rebuild(tmp_path)
    (tmp_path / "control/alpha_model_background_engine_policy.json").write_text(
        json.dumps({"cooldown_min": {"rebalance_plan": 9999, "predict": 9999, "king_trading": 9999}}),
        encoding="utf-8",
    )
    (tmp_path / "control/alpha_model_background_engine_state.json").write_text(
        json.dumps({"last_step_utc": {"rebalance_plan": "2026-06-08T08:00:00+00:00"}}),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "signal_date": "2026-06-05", "generated_at_utc": "2026-06-08T12:00:00+00:00"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_internet_latest.json").write_text(
        json.dumps({"internet_ok": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 400, "updated_at_utc": "2026-06-08T08:00:00+00:00"}),
        encoding="utf-8",
    )
    with patch(
        "analytics.r3_internet_requirement.require_internet_for",
        return_value={"allowed": True},
    ), patch(
        "analytics.prediction_operations.maybe_run_eod_prediction_switch",
        return_value={"ok": True, "skipped": True, "reason": "eod_not_due"},
    ), patch(
        "analytics.king_plan_integration.rebuild_investment_plan_with_king",
        return_value={
            "ok": True,
            "pipeline_synced": True,
            "investable_eur": 475.0,
            "pipeline_run_id": "abc",
            "t212_positions_count": 0,
        },
    ) as mock_rebuild, patch(
        "analytics.king_trading_assist.run_king_trading_assist",
        return_value={"step": "king_trading", "ok": True, "skipped": True},
    ), patch(
        "analytics.live_trading_operations.rebalance_status",
        return_value={"is_due": False},
    ), patch(
        "analytics.r3_freigabe.refresh_freigabe_evidence",
        return_value={"package_ready": True},
    ), patch(
        "analytics.r3_t212_prognosis.build_r3_t212_daily_prognosis",
        return_value={"ok": True},
    ), patch(
        "analytics.live_profile_governance.h1_backtest_status",
        return_value={"status": "MISSING"},
    ):
        doc = tick_alpha_model_background(tmp_path, force=False)
    mock_rebuild.assert_called_once()
    reb = next(s for s in doc["steps"] if s["step"] == "rebalance_plan")
    assert reb.get("forced_stale_rebuild") is True
    assert reb.get("skipped") is not True


def test_rebuild_marks_partial_when_orders_fail(tmp_path: Path) -> None:
    _seed_rebuild(tmp_path)
    broker = {
        "cash_eur": 500.0,
        "cash_breakdown": {"planning_cash_eur": 500.0, "total_account_value_eur": 500.0},
        "positions": [],
        "positions_count": 0,
        "credentials_configured": True,
        "connected": True,
        "last_sync_utc": "2026-06-08T12:00:00+00:00",
        "r3_planning_cash_eur": 500.0,
        "r3_investable_eur": 475.0,
        "source": "r3_t212_api_bond",
        "bond_sync_ok": True,
        "sync_errors": [],
    }
    with patch(
        "analytics.king_plan_integration.sync_t212_realtime_for_plan",
        return_value=broker,
    ), patch(
        "analytics.pilot_investment_plan.build_investment_plan",
        return_value={
            "investable_eur": 475.0,
            "allocations": [{"symbol": "STX", "side": "BUY", "target_eur": 200}],
            "summary_de": "Test",
            "signal_date": "2026-06-05",
        },
    ), patch(
        "analytics.pilot_day_trading_facade.refresh_trading_snapshot",
        return_value=type(
            "Snap",
            (),
            {
                "health": {"ok": True},
            },
        )(),
    ), patch(
        "analytics.r3_stock_orders.refresh_stock_order_evidence",
        side_effect=RuntimeError("orders boom"),
    ), patch(
        "analytics.pilot_investment_plan.ensure_plan_symbols_in_scope",
        return_value=False,
    ):
        out = rebuild_investment_plan_with_king(tmp_path, force_t212_sync=False)
    assert out.get("ok") is True
    assert out.get("partial") is True
    assert out.get("pipeline_synced") is False
    plan = json.loads((tmp_path / "evidence/pilot_investment_plan_latest.json").read_text())
    assert plan.get("pipeline_partial") is True
    loop = json.loads((tmp_path / "evidence/r3_closed_loop_latest.json").read_text())
    assert loop.get("loop_ok") is False
    assert loop.get("pipeline_partial") is True
