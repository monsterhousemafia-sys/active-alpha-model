from __future__ import annotations

import os
from pathlib import Path

import pytest

from execution.confirmed_live.p17_review_mode_guard import review_mode_active
from execution.confirmed_live.p17_review_mode_preferences import (
    apply_saved_review_mode_to_environment,
    load_review_mode_preference,
    set_review_mode_enabled,
)


def test_review_mode_default_on_without_pref(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", raising=False)
    monkeypatch.delenv("AA_NO_LIVE_ORDER_SUBMISSION", raising=False)
    enabled = apply_saved_review_mode_to_environment(tmp_path)
    assert enabled is True
    assert review_mode_active() is True


def test_review_mode_persist_off(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", raising=False)
    set_review_mode_enabled(tmp_path, enabled=False)
    pref = load_review_mode_preference(tmp_path)
    assert pref["review_mode_enabled"] is False
    apply_saved_review_mode_to_environment(tmp_path)
    assert review_mode_active() is False
    assert os.environ.get("AA_NO_LIVE_ORDER_SUBMISSION") == "0"


def test_review_mode_persist_on_after_off(tmp_path: Path, monkeypatch):
    set_review_mode_enabled(tmp_path, enabled=False)
    set_review_mode_enabled(tmp_path, enabled=True)
    apply_saved_review_mode_to_environment(tmp_path)
    assert review_mode_active() is True


def test_apple_toggle_switch_checked_state():
    from PySide6.QtWidgets import QApplication

    from ui.interactive_cockpit.apple_toggle_switch import AppleToggleSwitch

    app = QApplication.instance() or QApplication([])
    sw = AppleToggleSwitch()
    sw.setChecked(True)
    assert sw.isChecked() is True
    assert sw.knobPosition == pytest.approx(1.0)
    sw.setChecked(False)
    assert sw.knobPosition == pytest.approx(0.0)
