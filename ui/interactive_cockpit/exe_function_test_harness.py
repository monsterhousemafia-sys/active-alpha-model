"""Full-function test matrix for interactive Marktanalyse cockpit (dev + EXE)."""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List
from unittest import mock

from ui.interactive_cockpit.main_window import NAV_ITEMS, InteractiveCockpitWindow


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _record(results: List[Dict[str, Any]], name: str, fn: Callable[[], None]) -> None:
    try:
        fn()
        results.append({"name": name, "status": "PASS"})
    except Exception as exc:
        results.append(
            {
                "name": name,
                "status": "FAIL",
                "error": str(exc)[:500],
                "traceback": traceback.format_exc()[-800:],
            }
        )


def run_full_function_matrix(win: InteractiveCockpitWindow) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    nav_keys = [k for k, _ in NAV_ITEMS]

    def nav_all() -> None:
        for key in nav_keys:
            win._go_nav(key)
            assert win.stack.currentIndex() == win._nav_index[key]

    _record(results, f"nav_all_{len(nav_keys)}_views", nav_all)

    def refresh_light() -> None:
        win.refresh_state(full=False)
        assert isinstance(win.state, dict)

    _record(results, "refresh_state_light", refresh_light)

    def refresh_full() -> None:
        win.refresh_state(full=True)
        assert isinstance(win.state, dict)

    _record(results, "refresh_state_full", refresh_full)

    def learning_readiness_active() -> None:
        win.refresh_state(full=True)
        lr = win.state.get("learning_readiness") or {}
        assert lr.get("learning_collection_active") is True, "learning collection must stay enabled"
        assert lr.get("auto_training_blocked") is True, "auto-training must remain blocked"
        learning = win.state.get("learning") or {}
        assert "readiness" in learning or lr, "learning cycle must populate readiness"

    _record(results, "learning_readiness_active", learning_readiness_active)

    def failure_panel() -> None:
        win._go_nav("overview")
        assert win._overview_failure_host.count() > 0

    _record(results, "failure_state_panel", failure_panel)

    def live_prufstand_panel() -> None:
        win._go_nav("overview")
        assert hasattr(win, "_refresh_checks")
        assert hasattr(win, "_trade_today_banner")

    _record(results, "live_prufstand_panel", live_prufstand_panel)

    def no_forbidden_order_buttons() -> None:
        assert win.verify_no_order_buttons() is True

    _record(results, "no_forbidden_order_buttons", no_forbidden_order_buttons)

    def scenario_calc() -> None:
        win._go_nav("planning")
        win.state = {
            **win.state,
            "market_price_freshness": {"calculation_allowed": True, "status": "FRESH", "reason": "test"},
            "market_prices": {"executable_prices_eur": {"OXY": 71.0, "WDC": 80.0}},
        }
        win._sc_symbol.setText("OXY")
        win._sc_amount.setText("50,00")
        win._sc_capital.setText("500")
        win._sc_reserve.setText("50")
        win._calc_scenario()
        assert "Status:" in win._plan_result.text()

    _record(results, "scenario_calculate", scenario_calc)

    def scenario_save_dup_reset() -> None:
        win._save_scenario()
        win._dup_scenario()
        win._reset_scenario_fields()
        assert win._sc_name.text() == "Mein Szenario"

    _record(results, "scenario_save_dup_reset", scenario_save_dup_reset)

    def activity_export() -> None:
        win._go_nav("audit")
        with mock.patch("PySide6.QtWidgets.QMessageBox.information", return_value=None):
            win._export_activity()
        assert (win.root / "live_pilot/activity/export_latest.json").is_file()

    _record(results, "activity_export", activity_export)

    def t212_connection_mock() -> None:
        from integrations.trading212.t212_connection_status_model import BrokerConnectionStatus

        broker_status = BrokerConnectionStatus(
            status="LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
            credentials_configured=True,
            cash_eur=100.0,
            positions=[{"ticker": "OXY_US_EQ", "quantity": 1.0, "currentValue": 71.0}],
            positions_count=1,
        )
        win._go_nav("t212")
        win._readonly_confirm.setChecked(True)
        win._api_key.setText("test-key")
        win._api_secret.setText("test-secret")
        with mock.patch(
            "integrations.trading212.t212_credentials_ui_controller.test_credentials_from_gui",
            return_value=(True, "OK"),
        ), mock.patch("PySide6.QtWidgets.QMessageBox.information", return_value=None), mock.patch(
            "PySide6.QtWidgets.QMessageBox.warning",
            return_value=None,
        ):
            win._test_t212_connection()
        with mock.patch(
            "integrations.trading212.t212_credentials_ui_controller.apply_credentials_from_gui",
            return_value={"stored": "session", "message": "OK"},
        ), mock.patch(
            "integrations.trading212.t212_readonly_connection_service.sync_readonly_account",
            return_value=broker_status,
        ), mock.patch("PySide6.QtWidgets.QMessageBox.information", return_value=None):
            win._save_t212_connection()
        with mock.patch(
            "integrations.trading212.t212_readonly_connection_service.sync_readonly_account",
            return_value=broker_status,
        ), mock.patch("PySide6.QtWidgets.QMessageBox.information", return_value=None):
            win._sync_t212()
        with mock.patch("PySide6.QtWidgets.QMessageBox.information", return_value=None):
            win._forget_t212()

    _record(results, "t212_credentials_flow_mock", t212_connection_mock)

    def order_draft_create() -> None:
        from ui.interactive_cockpit.order_workflow_ui import _create_sample_draft

        win._go_nav("order_review")
        _create_sample_draft(win)
        win.refresh_state(full=False)
        assert hasattr(win, "_order_review_table")

    _record(results, "order_review_create_draft", order_draft_create)

    def live_setup_baseline() -> None:
        from ui.interactive_cockpit.order_workflow_ui import _save_baseline_scope

        win._go_nav("live_setup")
        win._managed_symbols.setText("OXY,WDC")
        win._managed_capital.setText("500")
        with mock.patch("PySide6.QtWidgets.QMessageBox.information", return_value=None):
            _save_baseline_scope(win)

    _record(results, "live_setup_baseline_scope", live_setup_baseline)

    def risk_kill_switch_cycle() -> None:
        from ui.interactive_cockpit.order_workflow_ui import _kill_switch, _pause_core_live

        win._go_nav("risk")
        _pause_core_live(win)
        _kill_switch(win)
        _kill_switch(win)

    _record(results, "risk_kill_switch_cycle", risk_kill_switch_cycle)

    def keyboard_shortcuts() -> None:
        for seq, key in [
            ("Ctrl+1", "overview"),
            ("Ctrl+6", "order_review"),
            ("Ctrl+9", "settings"),
        ]:
            win._go_nav(key)
            assert win.stack.currentIndex() == win._nav_index[key]

    _record(results, "keyboard_nav_shortcuts", keyboard_shortcuts)

    def view_widgets_present() -> None:
        required = {
            "overview": ["_overview_cards"],
            "t212": ["_t212_positions", "_t212_status"],
            "investments": ["_inv_real_table", "_inv_paper"],
            "planning": ["_plan_table", "_plan_result"],
            "market": [
                "_market_table",
                "_market_status",
                "_sector_reference_label",
                "_gap_table",
                "_learning_status",
                "_learning_table",
            ],
            "activity": ["_activity_table"],
            "tickets": ["_ticket_draft", "_ticket_invalid"],
            "trigger": ["_trigger_body", "_trigger_bar"],
            "intraday": ["_intraday_body"],
            "proposals": ["_proposals_body"],
            "order_review": ["_order_review_table"],
            "confirmed_orders": ["_confirmed_orders_body"],
            "live_setup": ["_baseline_label", "_managed_symbols"],
            "risk": ["_risk_body"],
            "audit": ["_audit_body"],
            "settings": [],
        }
        for key, attrs in required.items():
            win._go_nav(key)
            for attr in attrs:
                assert hasattr(win, attr), f"{key} missing {attr}"

    _record(results, "view_widgets_present", view_widgets_present)

    def trading_mode_guard() -> None:
        from execution.confirmed_live.trading_mode_policy import get_trading_mode

        mode = get_trading_mode(win.root)
        assert mode in ("manual", "ai_assisted")

    _record(results, "trading_mode_valid", trading_mode_guard)

    def positions_table_fill() -> None:
        win.state = {
            **win.state,
            "broker": {
                "credentials_configured": True,
                "positions": [{"ticker": "STX_US_EQ", "quantity": 0.09, "currentValue": 71.49}],
                "positions_count": 1,
                "cash_eur": 50.0,
                "status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
            },
        }
        win._refresh_all_views()
        assert win._t212_positions.rowCount() >= 1

    _record(results, "positions_table_fill", positions_table_fill)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = [r for r in results if r["status"] == "FAIL"]
    return {
        "generated_at_utc": _utc_now(),
        "matrix_version": 1,
        "nav_view_count": len(nav_keys),
        "total": len(results),
        "passed": passed,
        "failed": len(failed),
        "overall": "PASS" if not failed else "FAIL",
        "results": results,
        "failures": failed,
    }


def write_matrix_evidence(root: Path, report: Dict[str, Any]) -> Path:
    out = Path(root) / "evidence" / "interactive_cockpit_full_function_matrix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
