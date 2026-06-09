"""Tests for P16F desktop product and 50 EUR intraday trigger."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from intraday.trigger.intraday_unlock_policy import DAYTRADING_TRIGGER_REALIZED_NET_PROFIT_EUR
from intraday.trigger.realized_net_profit_trigger import (
    compute_realized_net_profit_eur,
    distance_to_trigger,
    evaluate_trigger_status,
)
from intraday.trigger.realized_profit_reconciliation_adapter import normalize_reconciled_trades
from intraday.trigger.trigger_state_store import ensure_id0_branch, update_trigger_state


def _trade(profit: float) -> dict:
    return {
        "reconciliation_status": "RECONCILED",
        "counts_toward_trigger": True,
        "side": "SELL",
        "realized_sale_proceeds_eur": 100 + profit,
        "realized_cost_basis_eur": 100,
        "actual_broker_fees_eur": 0,
        "actual_fx_costs_eur": 0,
        "other_actual_execution_costs_eur": 0,
    }


def test_trigger_threshold_boundaries() -> None:
    assert evaluate_trigger_status(profit_eur=49.99, broker_connected=True, has_reconciled_trades=True) == (
        "INACTIVE_REALIZED_NET_PROFIT_BELOW_50_EUR"
    )
    assert evaluate_trigger_status(profit_eur=50.00, broker_connected=True, has_reconciled_trades=True) == (
        "TRIGGER_REACHED_INTRADAY_PAPER_BRANCH_UNLOCKED"
    )
    assert evaluate_trigger_status(profit_eur=50.01, broker_connected=True, has_reconciled_trades=True) == (
        "TRIGGER_REACHED_INTRADAY_PAPER_BRANCH_UNLOCKED"
    )


def test_paper_and_deposits_excluded() -> None:
    trades = normalize_reconciled_trades(
        [
            {"source": "PAPER", "reconciliation_status": "RECONCILED", "side": "SELL"},
            {"category": "DEPOSIT", "reconciliation_status": "RECONCILED"},
            {"category": "DIVIDEND", "reconciliation_status": "RECONCILED"},
            _trade(60.0),
        ]
    )
    profit = compute_realized_net_profit_eur(trades)
    assert profit == 60.0
    assert len([t for t in trades if t.get("counts_toward_trigger")]) == 1


def test_unreconciled_excluded() -> None:
    trades = normalize_reconciled_trades([{"side": "SELL", "reconciliation_status": "PENDING"}])
    assert compute_realized_net_profit_eur(trades) == 0.0


def test_distance_to_trigger() -> None:
    assert distance_to_trigger(30.0) == 20.0
    assert distance_to_trigger(50.0) == 0.0
    assert distance_to_trigger(55.0) == 0.0


def test_id0_idempotent(tmp_path: Path) -> None:
    root = tmp_path
    state1 = update_trigger_state(
        root,
        reconciled_trades=[_trade(DAYTRADING_TRIGGER_REALIZED_NET_PROFIT_EUR)],
        broker_connected=True,
    )
    state2 = update_trigger_state(
        root,
        reconciled_trades=[_trade(DAYTRADING_TRIGGER_REALIZED_NET_PROFIT_EUR)],
        broker_connected=True,
    )
    assert state1["id0_intraday_paper_branch_unlocked"] is True
    assert state2["id0_intraday_paper_branch_unlocked"] is True
    branch_path = root / "intraday/id0_intraday_daytrading_research_foundation/branch_state.json"
    assert branch_path.is_file()
    assert ensure_id0_branch(root, trigger_status=state2["trigger_status"])["created_at_utc"]


def test_virtual_cash_not_real_authority(tmp_path: Path) -> None:
    from paper.p16f.real_cash_ledger import build_real_cash_state

    (tmp_path / "paper/p16d").mkdir(parents=True)
    (tmp_path / "paper/p16d/runtime_checkpoint.json").write_text(
        json.dumps({"cash_eur": 9999.0}), encoding="utf-8"
    )
    state = build_real_cash_state(tmp_path, readonly_broker_cash=None)
    assert state["available_real_manual_ticket_budget_eur"] == 0.0
    assert state["virtual_cash_used_as_real_cash_authority"] is False


def test_p16f_desktop_tabs(tmp_path: Path) -> None:
    from aa_decision_cockpit_p16f_desktop import build_p16f_desktop_tabs

    (tmp_path / "paper/p16f").mkdir(parents=True)
    (tmp_path / "paper/p16f/p16f_desktop_runtime_summary.json").write_text(
        json.dumps(
            {
                "p16f_desktop_status": "PASS_PROFESSIONAL_DESKTOP_PRODUCT_BUILT_TRIGGER_IMPLEMENTED_AWAITING_READONLY_REAL_INPUT",
                "trigger": {"trigger_status": "INACTIVE", "trigger_threshold_eur": 50.0},
                "gui_indicators": {"p16e_tickets_execution_allowed": False},
            }
        ),
        encoding="utf-8",
    )
    tabs = build_p16f_desktop_tabs(tmp_path)
    assert "P16F Dashboard" in tabs
    assert "Profit Trigger" in tabs
    assert "DO NOT EXECUTE" in tabs["Manual Tickets"]


def test_gui_widget_includes_p16f_tabs(tmp_path: Path) -> None:
    from aa_decision_cockpit_gui import create_decision_cockpit_widget_from_data
    from PySide6.QtWidgets import QApplication, QTabWidget

    QApplication.instance() or QApplication([])
    (tmp_path / "paper/p16f").mkdir(parents=True)
    (tmp_path / "paper/p16f/p16f_desktop_runtime_summary.json").write_text("{}", encoding="utf-8")
    widget = create_decision_cockpit_widget_from_data({}, root=tmp_path, include_p16f_desktop=True)
    tw = widget.findChild(QTabWidget)
    assert tw is not None
    titles = [tw.tabText(i) for i in range(tw.count())]
    assert "P16F Dashboard" in titles


def test_t212_write_blocked() -> None:
    from integrations.trading212.t212_health_status import build_t212_health_status

    h = build_t212_health_status()
    assert h["write_methods_blocked"] is True
    assert h["order_endpoints_blocked"] is True


def test_p16f_desktop_engine(tmp_path: Path) -> None:
    from paper.p16f.desktop_engine import run_p16f_desktop_product

    # Minimal tree — engine should fail-closed without full p16d/p16e artifacts
    (tmp_path / "outgoing_cursor_observation/p16e_fast_track_manual_live_readiness").mkdir(parents=True)
    zip_src = Path(__file__).resolve().parents[1] / "outgoing_cursor_observation/p16e_fast_track_manual_live_readiness"
    if not (zip_src / "cursor_p16e_fast_track_manual_live_readiness_package.zip").is_file():
        pytest.skip("P16E package not present locally")
    result = run_p16f_desktop_product(tmp_path)
    assert result["safety"]["broker_order_submitted_by_cursor"] is False
    assert result["safety"]["active_champion"] == "R3_w075_q065_noexit"
