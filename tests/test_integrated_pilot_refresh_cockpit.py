from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest


def test_apply_integrated_refresh_fail_soft(tmp_path: Path) -> None:
    from ui.interactive_cockpit.integrated_pilot_refresh import apply_integrated_pilot_refresh

    state: dict = {"refresh_error": None}
    with mock.patch(
        "analytics.pilot_integrated_refresh.run_integrated_refresh",
        side_effect=RuntimeError("broker down"),
    ):
        err = apply_integrated_pilot_refresh(tmp_path, state, force=True)
    assert err
    assert state.get("pilot_integrated_refresh_ok") is False
    assert "Live-Refresh" in (state.get("refresh_error") or "")


def test_trade_gate_summary_without_refresh_status() -> None:
    from ui.interactive_cockpit.integrated_pilot_refresh import trade_gate_summary

    val, sub, sev = trade_gate_summary({})
    assert val == "—"
    assert sev == "warn"


def test_trade_gate_summary_from_rows() -> None:
    from ui.interactive_cockpit.integrated_pilot_refresh import trade_gate_summary

    val, _, sev = trade_gate_summary(
        {
            "refresh_status": {
                "rows": [
                    {"key": "trade_gate", "status": "FAIL", "value_de": "Nein", "detail_de": "Kurse"},
                ],
                "summary_de": "Blocker",
            }
        }
    )
    assert val == "Nein"
    assert sev == "fail"


@pytest.fixture
def cockpit_win(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AA_ALLOW_MULTI_INSTANCE", "1")
    monkeypatch.setenv("AA_OFFLINE_COCKPIT_TEST", "1")
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "1")
    from PySide6.QtWidgets import QApplication
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow

    QApplication.instance() or QApplication([])
    return InteractiveCockpitWindow(tmp_path)


def test_overview_has_live_prufstand_widgets(cockpit_win) -> None:
    cockpit_win._go_nav("overview")
    assert hasattr(cockpit_win, "_refresh_checks")
    assert hasattr(cockpit_win, "_trade_today_banner")


def test_refresh_full_merges_pilot_patch(cockpit_win, monkeypatch) -> None:
    patch = {
        "broker": {"cash_eur": 100.0, "status": "OK"},
        "refresh_status": {
            "generated_at_utc": "2026-06-01T12:00:00+00:00",
            "summary_de": "OK",
            "all_ok": True,
            "rows": [{"key": "trade_gate", "status": "OK", "value_de": "Ja", "detail_de": "x", "label_de": "g"}],
        },
        "champion_guard": {"status_de": "OK", "champion_ok": True, "signals_ok": True},
        "investment_plan": {"primary_action": {"symbol": "INTC", "target_eur": 40}},
        "portfolio_reevaluation": {"summary_de": "ok", "rows": []},
        "market_prices": {"executable_prices_eur": {}, "freshness": {"status": "FRESH"}},
        "cost_risk": {"trade_allowed": True, "base_round_trip_eur": 0.5, "stress_round_trip_eur": 0.8},
    }

    class _Result:
        def as_state_patch(self):
            return patch

    monkeypatch.setattr(
        "analytics.pilot_integrated_refresh.run_integrated_refresh",
        lambda *a, **k: _Result(),
    )
    cockpit_win.refresh_state(full=True)
    assert cockpit_win.state.get("refresh_status")
    assert cockpit_win.state.get("pilot_integrated_refresh_ok") is True
    cockpit_win._go_nav("overview")
    assert cockpit_win._refresh_checks.rowCount() >= 1
