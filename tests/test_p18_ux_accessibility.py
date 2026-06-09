"""P18 UX, accessibility, and failure-state tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from ui.interactive_cockpit.services.failure_state_service import classify_system_state


def test_failure_state_not_configured():
    fs = classify_system_state({"broker": {"status": "NOT_CONFIGURED"}})
    assert fs["overall"] in ("INFO", "OK")
    assert any(i["code"] == "BROKER_NOT_CONFIGURED" for i in fs["issues"])


def test_failure_state_rate_limit():
    fs = classify_system_state({"broker": {"status": "ERROR", "last_error": "HTTP 429 rate limit"}})
    assert any(i["code"] == "BROKER_RATE_LIMIT" for i in fs["issues"])


def test_failure_state_kill_switch():
    fs = classify_system_state({"broker": {}, "p16h": {"kill_switch": {"active": True}}})
    assert fs["overall"] == "CRITICAL"


def test_failure_state_broker_ok():
    fs = classify_system_state(
        {
            "broker": {"status": "CONNECTED_READONLY_OK"},
            "cash": {"readonly_broker_cash_verified": True},
            "p17": {"review_mode_no_live_submission": True},
        }
    )
    assert fs["broker_online"] is True


def test_failure_state_stale_market_prices():
    fs = classify_system_state(
        {
            "broker": {"status": "NOT_CONFIGURED"},
            "market_price_freshness": {"status": "STALE", "reason": "too old"},
        }
    )
    assert any(i["code"] == "MARKET_PRICES_STALE" for i in fs["issues"])


def test_button_roles_default_secondary() -> None:
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget
    from ui.interactive_cockpit.button_roles import ROLE_NAV, ROLE_PRIMARY, ROLE_SECONDARY, apply_button_affordance, set_button_role

    QApplication.instance() or QApplication([])
    host = QWidget()
    plain = QPushButton("Aktion", host)
    set_button_role(QPushButton("Haupt", host), ROLE_PRIMARY)
    set_button_role(QPushButton("Nav", host), ROLE_NAV)
    apply_button_affordance(host)
    assert plain.objectName() == ROLE_SECONDARY


def test_accessibility_mode_badges():
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget
    from ui.interactive_cockpit.accessibility_helpers import mode_badge, tag_interactive_widgets

    QApplication.instance() or QApplication([])
    lbl = mode_badge("PAPER", "PAPER")
    assert "PAPER" in lbl.text()
    host = QWidget()
    btn = QPushButton("Test Aktion", host)
    tag_interactive_widgets(host)
    assert btn.accessibleName() == "Test Aktion"


def test_interactive_window_p18_smoke(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication
    from ui.interactive_cockpit.main_window import NAV_ITEMS, InteractiveCockpitWindow

    QApplication.instance() or QApplication([])
    win = InteractiveCockpitWindow(tmp_path)
    assert win.verify_no_order_buttons() is True
    assert win.stack.count() == len(NAV_ITEMS)
    assert hasattr(win, "_overview_failure_host")
    assert "P18" in win.windowTitle()


def test_p17_import_for_p18():
    from research.p18.p17_import_verification import verify_p17_import

    root = Path(__file__).resolve().parents[1]
    v = verify_p17_import(root)
    assert v.get("artefact_folder_found") is True


def test_onboarding_has_five_steps(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow
    from ui.interactive_cockpit.first_run_onboarding import FirstRunOnboardingDialog

    QApplication.instance() or QApplication([])
    win = InteractiveCockpitWindow(tmp_path)
    dlg = FirstRunOnboardingDialog(win)
    assert dlg.stack.count() == 5


def test_single_instance_lock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_SINGLE_INSTANCE", "1")
    from aa_single_instance import acquire_single_instance

    guard = acquire_single_instance(tmp_path, window_title="Marktanalyse")
    assert guard is not None
    guard.release()
