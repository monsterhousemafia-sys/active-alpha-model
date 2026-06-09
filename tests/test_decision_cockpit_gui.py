"""Tests for read-only Decision Cockpit GUI integration."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _offscreen_qt(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
    except Exception:
        pass
    yield


def _require_qt():
    from aa_dashboard_qt import qt_available

    if not qt_available():
        pytest.skip("PySide6 not installed")


def test_cockpit_widget_read_only_banners(tmp_path: Path):
    _require_qt()
    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_decision_cockpit_gui import build_cockpit_tab_labels, create_decision_cockpit_widget
    from aa_decision_cockpit_viewmodel import load_decision_cockpit

    root = _fixture_root(tmp_path)
    data = load_decision_cockpit(root)
    tabs = build_cockpit_tab_labels(data)
    assert "NO LIVE TRADING" in tabs["Overview"]
    assert "READ-ONLY" in tabs["Overview"]
    assert "BACKTESTED" in tabs["Overview"]
    assert "RESEARCH_ONLY" in tabs["Experiment"]
    widget = create_decision_cockpit_widget(root)
    assert widget.property("decision_cockpit_read_only") is True


def test_why_not_promoted_shows_blockers_and_conflicts(tmp_path: Path):
    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_decision_cockpit_gui import build_cockpit_tab_labels
    from aa_decision_cockpit_viewmodel import load_decision_cockpit

    data = load_decision_cockpit(_fixture_root(tmp_path))
    text = build_cockpit_tab_labels(data)["Why Not Promoted"]
    assert "Current active blockers:" in text
    assert "Source conflicts:" in text
    assert "CHALLENGER_TURNOVER_NOT_VERIFIED" in text
    assert "ECONOMIC_VALUE_GATE" in text


def test_gui_unknown_when_evidence_missing(tmp_path: Path):
    _require_qt()
    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_decision_cockpit_gui import build_cockpit_tab_labels
    from aa_decision_cockpit_viewmodel import load_decision_cockpit

    root = _fixture_root(tmp_path, include_champion=False)
    (root / "control" / "last_known_good_state.json").write_text("{}", encoding="utf-8")
    (root / "control" / "evidence" / "current_evidence_status.json").unlink()
    tabs = build_cockpit_tab_labels(load_decision_cockpit(root))
    assert "UNKNOWN" in tabs["Overview"]
    assert "BLOCKED FOR SAFETY" in tabs["Overview"]
    assert "BLOCKED" in tabs["Monitoring"]


def test_gui_shows_automation_safety_block(tmp_path: Path):
    import yaml

    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_decision_cockpit_gui import build_cockpit_tab_labels
    from aa_decision_cockpit_viewmodel import load_decision_cockpit

    root = _fixture_root(tmp_path)
    cfg = yaml.safe_load((root / "promotion_gate_config.yaml").read_text())
    cfg["auto_promote_paper_enabled"] = True
    (root / "promotion_gate_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
    tabs = build_cockpit_tab_labels(load_decision_cockpit(root))
    assert "UNSAFE OR UNVERIFIED AUTOMATION CONFIGURATION" in tabs["Safety"]
    assert "BLOCKED FOR SAFETY" in tabs["Safety"]


def test_gui_shows_hooks_safety_block(tmp_path: Path):
    import json

    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_decision_cockpit_gui import build_cockpit_tab_labels
    from aa_decision_cockpit_viewmodel import load_decision_cockpit

    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").write_text(
        json.dumps({"version": 1, "hooks": {"afterFileEdit": [{"command": "echo"}]}}), encoding="utf-8"
    )
    tabs = build_cockpit_tab_labels(load_decision_cockpit(root))
    assert "CURSOR HOOKS ACTIVE OR UNVERIFIED" in tabs["Safety"]


def test_gui_invalid_hook_schema_unknown(tmp_path: Path):
    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_decision_cockpit_gui import build_cockpit_tab_labels
    from aa_decision_cockpit_viewmodel import load_decision_cockpit

    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").write_text("{}", encoding="utf-8")
    tabs = build_cockpit_tab_labels(load_decision_cockpit(root))
    assert "UNKNOWN — BLOCKED FOR SAFETY" in tabs["Safety"]


def test_gui_dynamic_controller_state(tmp_path: Path):
    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_decision_cockpit_gui import build_cockpit_tab_labels
    from aa_decision_cockpit_viewmodel import load_decision_cockpit

    tabs = build_cockpit_tab_labels(load_decision_cockpit(_fixture_root(tmp_path)))
    assert "Current Executed Phase:" in tabs["Overview"]
    assert "V4R2 final fail-closed" not in tabs["Overview"]


def test_gui_experiment_blocked_unknown(tmp_path: Path):
    import yaml

    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_decision_cockpit_gui import build_cockpit_tab_labels
    from aa_decision_cockpit_viewmodel import load_decision_cockpit

    root = _fixture_root(tmp_path)
    path = root / "control" / "experiments" / "EXP_INITIAL_MOM_63_TOP12.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["decision_status"] = "PROMOTED"
    path.write_text(yaml.dump(manifest), encoding="utf-8")
    tabs = build_cockpit_tab_labels(load_decision_cockpit(root))
    assert "UNKNOWN — BLOCKED FOR SAFETY" in tabs["Experiment"]


def test_cockpit_no_operative_buttons(tmp_path: Path):
    _require_qt()
    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_decision_cockpit_gui import cockpit_widget_has_operative_actions, create_decision_cockpit_widget

    widget = create_decision_cockpit_widget(_fixture_root(tmp_path))
    assert cockpit_widget_has_operative_actions(widget) is False


def test_dashboard_has_cockpit_button_without_operative_label():
    _require_qt()
    from aa_dashboard_qt_window import AppSession

    AppSession._instance = None
    session = AppSession.get()
    win = session.window
    assert win._cockpit_btn.isEnabled()
    assert "Read-Only" in win._cockpit_btn.text()
    assert "Promote" not in win._cockpit_btn.text()
    session.stop_timer()
    AppSession._instance = None


def test_show_cockpit_does_not_modify_evidence(tmp_path: Path, monkeypatch):
    _require_qt()
    from tests.test_decision_cockpit_viewmodel import _fixture_root
    from aa_dashboard_qt_window import AppSession

    root = _fixture_root(tmp_path)
    monkeypatch.chdir(root)
    AppSession._instance = None
    session = AppSession.get()
    evidence = root / "control" / "evidence" / "current_evidence_status.json"
    before = evidence.read_bytes()
    session.window._show_decision_cockpit()
    assert evidence.read_bytes() == before
    session.stop_timer()
    AppSession._instance = None
