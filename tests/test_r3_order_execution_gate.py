"""Orders nur über R3 — Gate trennt Engine-Plan von Order-Ausführung."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_order_execution_gate import (
    check_order_execution_allowed,
    is_r3_order_source,
    load_order_execution_policy,
)


def test_policy_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_order_execution_policy(root)
    assert policy.get("status") == "AUTHORITATIVE"
    assert "USER_CLICK" in (policy.get("allowed_order_sources") or [])


def test_r3_sources_allowed() -> None:
    policy = load_order_execution_policy(Path(__file__).resolve().parents[1])
    assert is_r3_order_source("ORDER_WORKFLOW_DIALOG", policy)
    assert is_r3_order_source("LIVE_DASHBOARD_REBALANCE", policy)
    assert not is_r3_order_source("LIVE_BAT_REBALANCE", policy)
    assert not is_r3_order_source("background", policy)


def test_execute_live_rebalance_blocked_without_r3(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/pilot_day_trading.json").write_text(
        json.dumps({"live_trading": {"enabled": True}}),
        encoding="utf-8",
    )
    from analytics.live_trading_operations import execute_live_rebalance

    out = execute_live_rebalance(tmp_path, force=True, source="LIVE_BAT_REBALANCE")
    assert out.get("ok") is False
    assert out.get("mode") == "r3_order_surface_required"


def test_execute_live_rebalance_allowed_for_r3_click(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_ORDER_EXECUTION_TEST_BYPASS", "1")
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/pilot_day_trading.json").write_text(
        json.dumps({"live_trading": {"enabled": True}}),
        encoding="utf-8",
    )
    with patch(
        "analytics.live_trading_operations.rebalance_status",
        return_value={"is_due": True, "summary_de": "fällig"},
    ), patch(
        "execution.confirmed_live.live_trading_enablement.ensure_live_trading_enabled",
        return_value={"enabled": True},
    ), patch(
        "analytics.prediction_operations.ensure_prediction_before_orders",
        return_value={"ok": True, "skipped": True},
    ), patch(
        "analytics.live_trading_operations.sync_broker_and_quotes",
        return_value={"broker": {"cash_eur": 100.0}, "quote_snapshot": {}},
    ), patch(
        "analytics.live_trading_operations.run_champion_signal_update",
        return_value={"ok": True, "skipped": True},
    ), patch(
        "analytics.pilot_investment_plan.build_investment_plan",
        return_value={"allocations": []},
    ), patch(
        "analytics.pilot_investment_plan.ensure_plan_symbols_in_scope",
        return_value=True,
    ), patch(
        "analytics.pilot_portfolio_reevaluation.evaluate_live_portfolio_vs_champion",
        return_value={"recommended_actions": []},
    ), patch(
        "analytics.live_trading_operations.build_rebalance_orders",
        return_value=[],
    ):
        from analytics.live_trading_operations import execute_live_rebalance

        gate = check_order_execution_allowed(tmp_path, source="USER_CLICK")
        assert gate.get("allowed") is True


def test_walkforward_rebalance_blocked_without_r3(tmp_path: Path) -> None:
    from tests.r3_order_fixtures import seed_operator_api_complete

    seed_operator_api_complete(tmp_path)
    (tmp_path / "evidence").mkdir()
    from execution.confirmed_live.us_equity_deferred_intents import (
        process_deferred_intents_if_due,
        try_execute_walkforward_rebalance_now,
    )

    wf = try_execute_walkforward_rebalance_now(
        tmp_path,
        orders=[{"symbol": "SPY", "notional_eur": 10.0}],
        plan={},
        source="WALKFORWARD_REBALANCE_AUTO",
    )
    assert wf.get("ok") is False
    assert wf.get("mode") == "r3_order_surface_required"

    proc = process_deferred_intents_if_due(tmp_path)
    assert proc.get("executed") == 0
    assert "R3_ORDER_SURFACE_REQUIRED" in (proc.get("skipped") or [])


def test_bypass_ignored_outside_pytest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_ORDER_EXECUTION_TEST_BYPASS", "1")
    import sys

    saved = sys.modules.pop("pytest", None)
    try:
        gate = check_order_execution_allowed(tmp_path, source="LIVE_BAT_REBALANCE")
        assert gate.get("allowed") is False
    finally:
        if saved is not None:
            sys.modules["pytest"] = saved


def test_daily_cycle_does_not_auto_execute(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/pilot_day_trading.json").write_text(
        json.dumps(
            {
                "live_trading": {
                    "enabled": True,
                    "auto_execute_at_us_open": True,
                    "auto_enqueue_on_rebalance_due": True,
                }
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "analytics.live_trading_operations.sync_broker_and_quotes",
        return_value={"broker": {"cash_eur": 50.0, "credentials_configured": True}},
    ), patch(
        "analytics.live_trading_operations.record_daily_mark",
        return_value={"recorded": True},
    ), patch(
        "analytics.live_trading_operations.rebalance_status",
        return_value={"is_due": True, "summary_de": "Rebalance fällig"},
    ), patch(
        "analytics.live_trading_operations.enqueue_live_rebalance_when_due",
        return_value={"ok": True, "mode": "live_enqueue"},
    ) as mock_enqueue, patch(
        "analytics.live_trading_operations.execute_live_rebalance",
    ) as mock_exec:
        from analytics.live_trading_operations import run_daily_live_cycle

        run_daily_live_cycle(tmp_path, armed_auto=True, force_rebalance=False)
    mock_enqueue.assert_called_once()
    mock_exec.assert_not_called()
